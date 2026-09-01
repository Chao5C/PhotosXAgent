from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.services.geo_service import fetch_weather, geocode_place_name, haversine_km, resolve_photo_place
from app.services.rag_service import RagService
from app.services.session_service import SessionService
from app.utils.serialize import serialize, utcnow
from photosx.agents.analysis_agent import _format_reply, generate_guide, stream_travel_guide, weather_brief

logger = logging.getLogger(__name__)

NEAR_PLACE_KM = 20.0
WINDOW_HOURS = 2
TRAVEL_GAP_HOURS = 6
SPREAD_DAYS = 7
NEAR_HOME_KM = 20.0


def _parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class AnalysisService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.rag = RagService(db)
        self.sessions = SessionService(db)

    async def analyze(
        self,
        user_id: str,
        photo_ids: Optional[list[str]] = None,
        request_text: str = "",
    ) -> dict:
        photos = await self._load_photos(user_id, photo_ids)
        indexed = 0
        for photo in photos:
            await self.rag.index_photo(user_id, photo)
            indexed += 1

        trigger = await self.evaluate_trip(user_id, photos[-1] if photos else None)
        now = utcnow()
        doc = {
            "user_id": user_id,
            "photo_ids": [p.get("id") for p in photos if p.get("id")],
            "request_text": request_text,
            "status": "triggered" if trigger.get("triggered") else "stored",
            "trigger": trigger,
            "place": trigger.get("place"),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.analyses.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return serialize(doc) or doc

    async def push(
        self,
        user_id: str,
        analysis_id: str | None = None,
        photo_ids: Optional[list[str]] = None,
        force: bool = False,
    ) -> dict:
        analysis = None
        if analysis_id:
            try:
                analysis = await self.db.analyses.find_one({"_id": ObjectId(analysis_id), "user_id": user_id})
            except Exception:
                analysis = None
        if analysis is None:
            analysis = await self.db.analyses.find_one({"user_id": user_id}, sort=[("created_at", -1)])
        if analysis is None and photo_ids:
            analysis = await self.analyze(user_id, photo_ids, request_text="push")
            try:
                analysis = await self.db.analyses.find_one({"_id": ObjectId(analysis["id"])})
            except Exception:
                analysis = None
        if not analysis:
            return {"ok": False, "message": "暂无可推送的分析结果"}

        payload = await self._build_push_payload(user_id, serialize(analysis) or analysis, generate=True)
        rec_doc = {
            "user_id": user_id,
            "analysis_id": str(analysis["_id"]),
            "title": payload.get("title"),
            "body": payload.get("body"),
            "type": payload.get("type") or "travel_guide",
            "place": payload.get("place"),
            "photo_ids": payload.get("photo_ids") or [],
            "weather_brief": payload.get("weather_brief"),
            "read": False,
            "created_at": utcnow(),
        }
        inserted = await self.db.recommendations.insert_one(rec_doc)
        payload["recommendation_id"] = str(inserted.inserted_id)
        await self.db.analyses.update_one(
            {"_id": analysis["_id"]},
            {"$set": {"pushed_at": utcnow(), "guide": payload, "updated_at": utcnow()}},
        )
        if force:
            return {"ok": True, "forced": True, "payload": payload, "message": None}
        queued = await self.sessions.enqueue_push(user_id, payload)
        return {"ok": True, "forced": False, "payload": payload, **queued}

    async def evaluate_trip(self, user_id: str, current: Optional[dict]) -> dict:
        empty = {"triggered": False, "reason": "no_photo"}
        if not current:
            return empty
        meta = current.get("metadata") or {}
        lat, lng = meta.get("lat"), meta.get("lng")
        if lat is None or lng is None:
            return {"triggered": False, "reason": "no_gps"}

        cursor = self.db.photos.find(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "metadata.lat": {"$ne": None},
                "metadata.lng": {"$ne": None},
            }
        )
        photos = []
        async for doc in cursor:
            item = serialize(doc) or {}
            taken = _parse_dt((item.get("metadata") or {}).get("taken_at")) or _parse_dt(item.get("created_at"))
            item["_taken"] = taken
            if taken:
                photos.append(item)
        if len(photos) < 4:
            return {"triggered": False, "reason": "not_enough_photos"}

        home = await self._home_centroid(photos, exclude_id=current.get("id"))
        if not home:
            return {"triggered": False, "reason": "no_home"}
        distance = haversine_km(home, (float(lat), float(lng)))
        if distance <= settings.DISTANCE_THRESHOLD_KM:
            return {"triggered": False, "reason": "not_far_enough", "distance_km": round(distance, 2)}

        device = (meta.get("device_id") or meta.get("camera") or "").strip()
        current_taken = _parse_dt(meta.get("taken_at")) or _parse_dt(current.get("created_at"))
        if not current_taken:
            return {"triggered": False, "reason": "no_taken_at"}

        new_place = []
        old_place = []
        for photo in photos:
            pmeta = photo.get("metadata") or {}
            plat, plng = pmeta.get("lat"), pmeta.get("lng")
            if plat is None or plng is None:
                continue
            pdevice = (pmeta.get("device_id") or pmeta.get("camera") or "").strip()
            if device and pdevice and pdevice != device:
                continue
            if haversine_km((float(lat), float(lng)), (float(plat), float(plng))) <= NEAR_PLACE_KM:
                new_place.append(photo)
            if haversine_km(home, (float(plat), float(plng))) <= NEAR_HOME_KM:
                old_place.append(photo)

        new_place.sort(key=lambda p: p["_taken"])
        window = self._find_window(new_place, timedelta(hours=WINDOW_HOURS), min_count=3)
        if not window:
            return {"triggered": False, "reason": "no_2h_window", "distance_km": round(distance, 2)}
        if window[-1]["_taken"] - window[0]["_taken"] > timedelta(days=SPREAD_DAYS):
            return {"triggered": False, "reason": "spread_over_7_days"}

        latest_new = max(window, key=lambda p: p["_taken"])
        old_before = [p for p in old_place if p["_taken"] < latest_new["_taken"]]
        if not old_before:
            return {"triggered": False, "reason": "no_previous_home_photo"}
        prev_old = max(old_before, key=lambda p: p["_taken"])
        if latest_new["_taken"] - prev_old["_taken"] >= timedelta(hours=TRAVEL_GAP_HOURS):
            return {"triggered": False, "reason": "travel_gap_too_long"}

        place = resolve_photo_place(current.get("geo") or {}, current.get("metadata") or {})
        recent = await self.db.analyses.find_one(
            {
                "user_id": user_id,
                "status": "triggered",
                "place": place,
                "created_at": {"$gte": utcnow() - timedelta(days=3)},
            }
        )
        if recent:
            return {"triggered": False, "reason": "already_triggered", "place": place}

        weather = (current.get("geo") or {}).get("weather")
        if not weather and lat is not None:
            weather = await fetch_weather(float(lat), float(lng))

        return {
            "triggered": True,
            "reason": "ok",
            "distance_km": round(distance, 2),
            "place": place,
            "device_id": device,
            "photo_ids": [p.get("id") for p in window],
            "prev_old_photo_id": prev_old.get("id"),
            "weather": weather,
            "weather_brief": weather_brief(weather),
        }

    def _find_window(self, photos: list[dict], span: timedelta, min_count: int) -> list[dict]:
        best: list[dict] = []
        for i, start in enumerate(photos):
            group = [start]
            for nxt in photos[i + 1 :]:
                if nxt["_taken"] - start["_taken"] <= span:
                    group.append(nxt)
                else:
                    break
            if len(group) >= min_count and len(group) >= len(best):
                best = group
        return best

    async def _home_centroid(self, photos: list[dict], exclude_id: str | None) -> Optional[tuple[float, float]]:
        lats, lngs = [], []
        for photo in photos:
            if photo.get("id") == exclude_id:
                continue
            meta = photo.get("metadata") or {}
            if meta.get("lat") is None or meta.get("lng") is None:
                continue
            lats.append(float(meta["lat"]))
            lngs.append(float(meta["lng"]))
        if len(lats) < 3:
            return None
        return (sum(lats) / len(lats), sum(lngs) / len(lngs))

    async def travel_advice_for_place(
        self,
        user_id: str,
        destination: str,
        user_question: str = "",
    ) -> dict:
        dest = (destination or "").strip()
        if not dest:
            return {"ok": False, "reply": "请告诉我你想去的城市或目的地，我再帮你写攻略。"}

        context = await self._build_travel_context(user_id, dest, user_question)
        guide = await generate_guide(context)
        guide["place"] = context["place"]
        guide["weather_brief"] = context["weather_brief"]
        reply = _format_reply(
            guide,
            related_photo_count=len(context.get("photos") or []),
            place=context["place"],
        )
        await self.sessions.save_last_guide(user_id, guide)

        return {
            "ok": True,
            "reply": reply,
            "title": guide.get("title"),
            "body": guide.get("body"),
            "highlights": guide.get("highlights") or [],
            "follow_up": guide.get("follow_up") or "",
            "place": context["place"],
            "weather_brief": context["weather_brief"],
            "related_photo_count": len(context.get("photos") or []),
            "guide": guide,
        }

    async def stream_travel_advice(
        self,
        user_id: str,
        destination: str,
        user_question: str = "",
    ):
        context = await self._build_travel_context(user_id, destination, user_question)
        async for event in stream_travel_guide(context):
            if event.get("type") == "done":
                guide = event.get("guide") or {}
                guide["place"] = context["place"]
                guide["weather_brief"] = context["weather_brief"]
                event["guide"] = guide
                event["reply"] = _format_reply(
                    guide,
                    related_photo_count=len(context.get("photos") or []),
                    place=context["place"],
                )
            yield event

    async def _build_travel_context(self, user_id: str, destination: str, user_question: str) -> dict:
        from app.services.mcp_gateway_service import mcp_fetch_weather, mcp_geocode_place

        geo = await mcp_geocode_place(self.db, destination)
        if not geo:
            geo = await geocode_place_name(destination)
        lat, lng = geo.get("lat"), geo.get("lng")
        weather = None
        if lat is not None and lng is not None:
            mcp_weather = await mcp_fetch_weather(self.db, float(lat), float(lng))
            weather = (mcp_weather or {}).get("weather") if mcp_weather else None
            if weather is None:
                weather = await fetch_weather(float(lat), float(lng))
        place_name = geo.get("city") or geo.get("place_name") or geo.get("display_name") or destination
        related = await self._photos_in_city(user_id, destination, limit=6)
        compact = [self.rag.compact_photo(p) for p in related]
        return {
            "place": place_name,
            "destination_query": destination,
            "user_question": (user_question or "").strip() or f"想去{destination}有什么建议",
            "weather": weather,
            "weather_brief": weather_brief(weather),
            "lat": lat,
            "lng": lng,
            "photos": compact,
            "captions": [p.get("caption") for p in compact if p.get("caption")],
            "intent": "travel_advice",
        }

    @staticmethod
    def guide_from_history(history: list[dict]) -> dict | None:
        for item in reversed(history or []):
            if item.get("role") != "assistant":
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            if len(lines) < 2:
                continue
            title = lines[0]
            body_parts = []
            highlights = []
            follow_up = ""
            for line in lines[1:]:
                if line.startswith("推荐关注："):
                    highlights = [part.strip() for part in line.replace("推荐关注：", "").split("；") if part.strip()]
                elif line.startswith("已参考") or line.startswith("联网资料"):
                    continue
                elif "？" in line or "?" in line:
                    follow_up = line
                else:
                    body_parts.append(line)
            body = "\n".join(body_parts).strip()
            if title and body:
                return {
                    "title": title,
                    "body": body,
                    "highlights": highlights,
                    "follow_up": follow_up,
                    "source": "history",
                }
        return None

    async def _photos_in_city(self, user_id: str, city: str, limit: int = 6) -> list[dict]:
        needle = (city or "").strip()
        if not needle:
            return []
        filters = {
            "user_id": user_id,
            "status": {"$ne": "deleted"},
            "$or": [
                {"geo.city": {"$regex": needle, "$options": "i"}},
                {"geo.place_name": {"$regex": needle, "$options": "i"}},
                {"geo.display_name": {"$regex": needle, "$options": "i"}},
            ],
        }
        cursor = self.db.photos.find(filters).sort("created_at", -1).limit(limit)
        return [serialize(d) for d in await cursor.to_list(limit) if d]

    async def _load_photos(self, user_id: str, photo_ids: Optional[list[str]]) -> list[dict]:
        if photo_ids:
            oids = []
            for pid in photo_ids:
                try:
                    oids.append(ObjectId(pid))
                except Exception:
                    continue
            cursor = self.db.photos.find({"_id": {"$in": oids}, "user_id": user_id})
            docs = {str(d["_id"]): serialize(d) for d in await cursor.to_list(len(oids) or 1)}
            return [docs[pid] for pid in photo_ids if pid in docs]
        cursor = self.db.photos.find({"user_id": user_id, "status": {"$ne": "deleted"}}).sort("created_at", -1).limit(8)
        return [serialize(d) for d in await cursor.to_list(8) if d]

    async def _build_push_payload(self, user_id: str, analysis: dict, generate: bool = True) -> dict:
        trigger = analysis.get("trigger") or analysis
        photo_ids = trigger.get("photo_ids") or analysis.get("photo_ids") or []
        photos = await self.rag.photos_by_ids(user_id, photo_ids)
        compact = [self.rag.compact_photo(p) for p in photos]
        context = {
            "place": trigger.get("place") or analysis.get("place"),
            "distance_km": trigger.get("distance_km"),
            "weather": trigger.get("weather"),
            "weather_brief": trigger.get("weather_brief") or weather_brief(trigger.get("weather")),
            "photos": compact,
            "captions": [p.get("caption") for p in compact],
        }
        guide = await generate_guide(context) if generate else {}
        return {
            "kind": "push",
            "type": "travel_guide",
            "topic": "travel",
            "title": guide.get("title") or f"新地点：{context['place'] or '未知'}",
            "body": guide.get("body") or context["weather_brief"],
            "place": context["place"],
            "weather_brief": context["weather_brief"],
            "photo_ids": photo_ids,
            "photos": compact,
            "highlights": guide.get("highlights") or [],
            "analysis_id": analysis.get("id"),
        }
