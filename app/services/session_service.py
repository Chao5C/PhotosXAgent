from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.serialize import serialize, utcnow
#会话状态机配置
ACTIVE_MINUTES = 5
IDLE_MAX_MINUTES = 30


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SessionService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def touch(self, user_id: str) -> str:
        now = utcnow()
        await self.db.user_sessions.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "last_message_at": now, "state": "ACTIVE", "updated_at": now}},
            upsert=True,
        )
        return "ACTIVE"

    def classify_state(self, last_message_at: datetime | None, now: datetime | None = None) -> str:
        now = now or utcnow()
        last = _aware(last_message_at)
        if last is None:
            return "DORMANT"
        delta = now - last
        if delta <= timedelta(minutes=ACTIVE_MINUTES):
            return "ACTIVE"
        if delta <= timedelta(minutes=IDLE_MAX_MINUTES):
            return "IDLE"
        return "DORMANT"

    async def get_state(self, user_id: str) -> str:
        doc = await self.db.user_sessions.find_one({"user_id": user_id})
        return self.classify_state((doc or {}).get("last_message_at"))

    async def get_memory(self, user_id: str) -> dict:
        doc = await self.db.user_memory.find_one({"user_id": user_id}) or {}
        return {
            "facts": doc.get("facts") or [],
            "mute_topics": doc.get("mute_topics") or [],
            "settings": doc.get("settings") or {},
            "reminders": doc.get("reminders") or [],
        }

    async def add_fact(self, user_id: str, fact: str) -> dict:
        fact = (fact or "").strip()
        if not fact:
            return await self.get_memory(user_id)
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {"$addToSet": {"facts": fact}, "$set": {"updated_at": utcnow()}, "$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )
        return await self.get_memory(user_id)

    async def mute_topic(self, user_id: str, topic: str, mute: bool = True) -> dict:
        topic = (topic or "").strip()
        op = "$addToSet" if mute else "$pull"
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {op: {"mute_topics": topic}, "$set": {"updated_at": utcnow()}, "$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )
        return await self.get_memory(user_id)

    async def add_reminder(self, user_id: str, text: str, fire_at: datetime, extra: Optional[dict] = None) -> dict:
        item = {
            "id": str(ObjectId()),
            "text": text,
            "fire_at": fire_at,
            "done": False,
            "created_at": utcnow(),
            **(extra or {}),
        }
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {"$push": {"reminders": item}, "$set": {"updated_at": utcnow()}, "$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )
        return item

    async def save_last_guide(self, user_id: str, guide: dict) -> None:
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {"$set": {"last_guide": guide, "updated_at": utcnow()}, "$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )

    async def get_last_guide(self, user_id: str) -> dict | None:
        doc = await self.db.user_memory.find_one({"user_id": user_id}) or {}
        guide = doc.get("last_guide")
        return dict(guide) if isinstance(guide, dict) and guide.get("body") else None

    async def mark_poster_offer(self, user_id: str) -> None:
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {"$set": {"poster_offer_pending": True, "updated_at": utcnow()}, "$setOnInsert": {"user_id": user_id}},
            upsert=True,
        )

    async def clear_poster_offer(self, user_id: str) -> None:
        await self.db.user_memory.update_one(
            {"user_id": user_id},
            {"$set": {"poster_offer_pending": False, "updated_at": utcnow()}},
            upsert=True,
        )

    async def enqueue_push(self, user_id: str, payload: dict) -> dict:
        now = utcnow()
        doc = {
            "user_id": user_id,
            "status": "pending",
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.push_queue.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        state = await self.get_state(user_id)
        if state != "ACTIVE":
            delivered = await self.deliver_pending(user_id, merge=state == "DORMANT")
            return {"queued": False, "state": state, "delivered": delivered}
        return {"queued": True, "state": state, "id": doc["id"]}

    async def deliver_pending(self, user_id: str, merge: bool = False) -> list[dict]:
        memory = await self.get_memory(user_id)
        mute = {str(t).lower() for t in memory.get("mute_topics") or []}
        cursor = self.db.push_queue.find({"user_id": user_id, "status": "pending"}).sort("created_at", 1)
        pending = await cursor.to_list(50)
        if not pending:
            return []
        now = utcnow()
        delivered: list[dict] = []

        def muted(payload: dict) -> bool:
            topic = str(payload.get("topic") or payload.get("type") or payload.get("place") or "").lower()
            body = str(payload.get("body") or payload.get("title") or "").lower()
            return any(m and (m in topic or m in body) for m in mute)

        keep = [p for p in pending if not muted(p.get("payload") or {})]
        skip_ids = [p["_id"] for p in pending if muted(p.get("payload") or {})]
        if skip_ids:
            await self.db.push_queue.update_many(
                {"_id": {"$in": skip_ids}},
                {"$set": {"status": "muted", "updated_at": now}},
            )

        groups: list[list[dict]]
        if merge and len(keep) > 1:
            groups = [keep]
        else:
            groups = [[item] for item in keep]

        for group in groups:
            payloads = [item.get("payload") or {} for item in group]
            if len(payloads) == 1:
                payload = payloads[0]
                content = payload.get("body") or payload.get("title") or "你有一条新的行程建议。"
                title = payload.get("title")
                if title and title not in content:
                    content = f"{title}\n{content}"
            else:
                lines = ["你离开助手一段时间了，这里合并了几条建议："]
                for payload in payloads:
                    title = payload.get("title") or "建议"
                    body = payload.get("body") or ""
                    lines.append(f"- {title}：{body}")
                content = "\n".join(lines)
                payload = {"title": "合并推送", "body": content, "type": "merged", "items": payloads}
            msg = {
                "user_id": user_id,
                "role": "assistant",
                "content": content,
                "kind": payload.get("kind") or "push",
                "photos": payload.get("photos") or [],
                "albums": payload.get("albums") or [],
                "intent": "PUSH",
                "created_at": now,
            }
            inserted = await self.db.chat_messages.insert_one(msg)
            msg["id"] = str(inserted.inserted_id)
            await self.db.push_queue.update_many(
                {"_id": {"$in": [item["_id"] for item in group]}},
                {"$set": {"status": "delivered", "delivered_at": now, "updated_at": now}},
            )
            delivered.append(serialize(msg) or msg)
        return delivered

    async def deliver_reminder(self, user_id: str, reminder_item: dict) -> dict:
        now = utcnow()
        content = (reminder_item.get("text") or "").strip() or "你设置的提醒时间到了。"
        msg = {
            "user_id": user_id,
            "role": "assistant",
            "content": f"⏰ 提醒：{content}",
            "kind": "reminder",
            "intent": "REMINDER",
            "reminder_id": reminder_item.get("id"),
            "created_at": now,
        }
        inserted = await self.db.chat_messages.insert_one(msg)
        msg["id"] = str(inserted.inserted_id)
        return serialize(msg) or msg

    async def due_reminders(self) -> list[dict]:
        now = utcnow()
        cursor = self.db.user_memory.find({"reminders.done": False})
        due = []
        async for doc in cursor:
            user_id = doc.get("user_id")
            reminders = doc.get("reminders") or []
            changed = False
            for item in reminders:
                if item.get("done"):
                    continue
                fire_at = _aware(item.get("fire_at"))
                if fire_at and fire_at <= now:
                    item["done"] = True
                    item["done_at"] = now
                    changed = True
                    due.append({"user_id": user_id, **item})
            if changed:
                await self.db.user_memory.update_one({"_id": doc["_id"]}, {"$set": {"reminders": reminders, "updated_at": now}})
        return due

    async def inbox_since(self, user_id: str, since: Optional[datetime] = None, kinds: Optional[list[str]] = None) -> list[dict]:
        filters: dict[str, Any] = {"user_id": user_id, "role": "assistant"}
        if since:
            filters["created_at"] = {"$gt": since}
        if kinds:
            filters["kind"] = {"$in": kinds}
        cursor = self.db.chat_messages.find(filters).sort("created_at", 1).limit(40)
        return [serialize(doc) for doc in await cursor.to_list(40) if doc]
