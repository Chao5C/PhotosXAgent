from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.serialize import parse_object_id, serialize, utcnow

EMBED_DIM = 256
NEAR_DUP = 0.999


def _tokenize(text: str) -> list[str]:
    text = (text or "").strip().lower()
    if not text:
        return []
    parts = re.split(r"[\s,，、;；|/]+", text)
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        tokens.append(part)
        for i, ch in enumerate(part):
            tokens.append(ch)
            if i + 1 < len(part):
                tokens.append(part[i : i + 2])
    return tokens


def embed_text(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    for token in _tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % EMBED_DIM
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def short_text(photo: dict) -> str:
    vision = photo.get("vision") or {}
    geo = photo.get("geo") or {}
    tags = vision.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    caption = photo_display_caption(photo)
    long_desc = photo_display_long_description(photo)
    parts = [
        *tags,
        vision.get("scene_type") or "",
        geo.get("city") or "",
        geo.get("place_name") or "",
        caption if caption and caption != (photo.get("filename") or "") else "",
        long_desc[:80] if long_desc else "",
    ]
    return " ".join(str(p).strip() for p in parts if p)


def photo_display_caption(photo: dict) -> str:
    ai = ((photo.get("vision") or {}).get("caption") or "").strip()
    user = (photo.get("user_description") or "").strip()
    fallback = "已提取拍摄信息，视觉模型未配置或调用失败。"
    if user:
        return user
    if ai and ai != fallback:
        return ai
    return ai or photo.get("filename") or ""


def photo_brief_caption(photo: dict) -> str:
    """Title line: prefer AI brief caption, then user override, then filename."""
    ai = ((photo.get("vision") or {}).get("caption") or "").strip()
    user = (photo.get("user_description") or "").strip()
    fallback = "已提取拍摄信息，视觉模型未配置或调用失败。"
    if ai and ai != fallback:
        return ai
    if user:
        return user
    return ai or photo.get("filename") or "暂无描述"


def photo_display_long_description(photo: dict) -> str:
    user = (photo.get("user_long_description") or "").strip()
    ai = ((photo.get("vision") or {}).get("long_description") or "").strip()
    if user:
        return user
    return ai


SCENE_QUERY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pet", ("宠物照", "宠物", "猫照", "狗照", "小动物", "必须是宠物", "只要宠物", "仅宠物", "只要猫", "只要狗")),
    ("scenery", ("风景照", "风光", "风景", "必须是风景", "只要风景")),
    ("food", ("美食", "食物", "必须是美食", "只要美食")),
    ("architecture", ("建筑", "建筑照", "必须是建筑", "只要建筑")),
    ("group", ("合照", "合影", "必须是合照", "只要合照")),
]

PET_HINTS = ("猫", "狗", "犬", "宠", "pet", "猫科", "犬科")


def infer_scene_filter(query: str) -> str | None:
    q = (query or "").strip()
    if not q:
        return None
    for scene, keywords in SCENE_QUERY_RULES:
        if any(kw in q for kw in keywords):
            return scene
    return None


def photo_matches_scene_filter(photo: dict, scene_type: str | None) -> bool:
    if not scene_type:
        return True
    vision = photo.get("vision") or {}
    if (vision.get("scene_type") or "") == scene_type:
        return True
    if scene_type != "pet":
        return False
    blob = " ".join(
        [
            " ".join(str(t) for t in (vision.get("tags") or [])),
            " ".join(str(t) for t in (vision.get("objects") or [])),
            str(vision.get("caption") or ""),
            str(photo.get("user_description") or ""),
        ]
    ).lower()
    return any(hint in blob for hint in PET_HINTS)


def long_text(photo: dict) -> str:
    vision = photo.get("vision") or {}
    geo = photo.get("geo") or {}
    meta = photo.get("metadata") or {}
    objects = vision.get("objects") or []
    tags = vision.get("tags") or []
    return "\n".join(
        [
            f"简略描述: {photo_brief_caption(photo)}",
            f"详细描述: {photo_display_long_description(photo)}",
            f"用户备注: {photo.get('user_description') or ''}",
            f"标签: {', '.join(tags) if isinstance(tags, list) else tags}",
            f"物体: {', '.join(objects) if isinstance(objects, list) else objects}",
            f"场景: {vision.get('scene_type') or ''}",
            f"人数: {vision.get('people_count') if vision.get('people_count') is not None else ''}",
            f"地点: {geo.get('place_name') or geo.get('city') or ''}",
            f"地标: {vision.get('landmark_hint') or ''}",
            f"拍摄时间: {meta.get('taken_at') or ''}",
            f"设备: {meta.get('camera') or meta.get('device_id') or ''}",
            f"文件名: {photo.get('filename') or ''}",
        ]
    )


class RagService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def index_photo(self, user_id: str, photo: dict) -> None:
        photo_id = photo.get("id") or str(photo.get("_id"))
        if not photo_id:
            return
        now = utcnow()
        for kind, text in (("short", short_text(photo)), ("long", long_text(photo))):
            await self.db.photo_chunks.update_one(
                {"user_id": user_id, "photo_id": photo_id, "kind": kind},
                {
                    "$set": {
                        "user_id": user_id,
                        "photo_id": photo_id,
                        "kind": kind,
                        "text": text,
                        "embedding": embed_text(text),
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

    async def _scene_allowed_ids(self, user_id: str, scene_type: str) -> set[str]:
        base = {"user_id": user_id, "status": {"$ne": "deleted"}}
        allowed: set[str] = set()
        cursor = self.db.photos.find({**base, "vision.scene_type": scene_type}, {"_id": 1})
        async for doc in cursor:
            allowed.add(str(doc["_id"]))
        if scene_type == "pet":
            extra_filter = {
                **base,
                "vision.scene_type": {"$ne": "pet"},
                "$or": [
                    {"vision.tags": {"$regex": "猫|狗|犬|宠物", "$options": "i"}},
                    {"vision.caption": {"$regex": "猫|狗|犬|宠物", "$options": "i"}},
                    {"vision.objects": {"$regex": "猫|狗|犬|宠物", "$options": "i"}},
                ],
            }
            cursor = self.db.photos.find(extra_filter, {"_id": 1})
            async for doc in cursor:
                allowed.add(str(doc["_id"]))
        return allowed

    async def search_short(
        self,
        user_id: str,
        query: str,
        top_k: int = 20,
        extra_ids: Optional[list[str]] = None,
        scene_type: Optional[str] = None,
        scan_limit: int = 800,
    ) -> list[str]:
        query = (query or "").strip()
        qvec = embed_text(query) if query else None
        allowed: set[str] | None = None
        if scene_type:
            allowed = await self._scene_allowed_ids(user_id, scene_type)
            if not allowed:
                return [pid for pid in (extra_ids or []) if pid][:top_k]

        cursor = self.db.photo_chunks.find({"user_id": user_id, "kind": "short"})
        scored: list[tuple[float, str]] = []
        scanned = 0
        async for doc in cursor:
            scanned += 1
            if scanned > scan_limit:
                break
            pid = doc.get("photo_id")
            if not pid or (allowed is not None and pid not in allowed):
                continue
            score = cosine(qvec, doc.get("embedding") or []) if qvec else 0.0
            text = doc.get("text") or ""
            if query:
                lowered = query.lower()
                if lowered in text.lower():
                    score += 0.35
                for token in _tokenize(query):
                    if token and token in text.lower():
                        score += 0.05
            scored.append((score, pid))
        scored.sort(key=lambda item: item[0], reverse=True)
        ids: list[str] = []
        seen = set()
        for score, pid in scored:
            if pid in seen:
                continue
            if qvec and score < 0.08 and query:
                continue
            seen.add(pid)
            ids.append(pid)
            if len(ids) >= top_k:
                break
        for pid in extra_ids or []:
            if pid in seen:
                continue
            if allowed is not None and pid not in allowed:
                continue
            seen.add(pid)
            ids.append(pid)
            if len(ids) >= top_k:
                break
        if query and len(ids) < top_k:
            filters: dict = {"user_id": user_id, "status": {"$ne": "deleted"}}
            if allowed is not None:
                oids = []
                for pid in allowed:
                    try:
                        oids.append(parse_object_id(pid, field="photo_id"))
                    except ValueError:
                        continue
                if not oids:
                    return ids
                filters["_id"] = {"$in": oids}
            regex_filter = {
                **filters,
                "$or": [
                    {"filename": {"$regex": query, "$options": "i"}},
                    {"vision.caption": {"$regex": query, "$options": "i"}},
                    {"user_description": {"$regex": query, "$options": "i"}},
                    {"vision.tags": {"$regex": query, "$options": "i"}},
                    {"geo.place_name": {"$regex": query, "$options": "i"}},
                    {"geo.city": {"$regex": query, "$options": "i"}},
                ],
            }
            cursor = self.db.photos.find(regex_filter).sort("created_at", -1).limit(top_k)
            async for doc in cursor:
                pid = str(doc["_id"])
                if pid in seen:
                    continue
                seen.add(pid)
                ids.append(pid)
                if len(ids) >= top_k:
                    break
        return ids

    async def load_long(self, user_id: str, photo_id: str) -> str:
        if not photo_id:
            return ""
        doc = await self.db.photo_chunks.find_one(
            {"user_id": user_id, "photo_id": photo_id, "kind": "long"}
        )
        if doc and doc.get("text"):
            return doc["text"]
        try:
            oid = parse_object_id(photo_id, field="photo_id")
        except ValueError:
            return ""
        photo = await self.db.photos.find_one({"_id": oid, "user_id": user_id})
        return long_text(serialize(photo) or {}) if photo else ""

    async def load_long_many(self, user_id: str, photo_ids: list[str]) -> dict[str, str]:
        result = {}
        for pid in photo_ids:
            result[pid] = await self.load_long(user_id, pid)
        return result

    async def photos_by_ids(self, user_id: str, photo_ids: list[str]) -> list[dict]:
        if not photo_ids:
            return []
        oids = []
        for pid in photo_ids:
            try:
                oids.append(ObjectId(pid))
            except Exception:
                continue
        if not oids:
            return []
        cursor = self.db.photos.find(
            {"_id": {"$in": oids}, "user_id": user_id, "status": {"$ne": "deleted"}}
        )
        docs = {str(doc["_id"]): serialize(doc) for doc in await cursor.to_list(len(oids))}
        return [docs[pid] for pid in photo_ids if pid in docs]

    async def index_search_results(
        self,
        user_id: str,
        query: str,
        *,
        scene_type: str | None = None,
        limit: int = 500,
    ) -> list[str]:
        """Build the full ranked id list for pagination (lazy, on view-more)."""
        return await self.search_short(
            user_id,
            query,
            top_k=limit,
            scene_type=scene_type,
            scan_limit=max(limit * 4, 800),
        )

    async def ensure_chat_search_indexed(self, doc: dict) -> list[str]:
        if doc.get("indexed") and doc.get("photo_ids"):
            return doc.get("photo_ids") or []
        all_ids = await self.index_search_results(
            doc["user_id"],
            doc.get("query") or "",
            scene_type=doc.get("scene_type"),
        )
        await self.db.chat_searches.update_one(
            {"_id": doc["_id"]},
            {"$set": {"photo_ids": all_ids, "indexed": True, "indexed_at": utcnow()}},
        )
        return all_ids

    def compact_photo(self, photo: dict) -> dict[str, Any]:
        vision = photo.get("vision") or {}
        geo = photo.get("geo") or {}
        meta = photo.get("metadata") or {}
        return {
            "id": photo.get("id"),
            "filename": photo.get("filename"),
            "caption": photo_display_caption(photo),
            "brief_caption": photo_brief_caption(photo),
            "long_description": photo_display_long_description(photo),
            "ai_caption": vision.get("caption"),
            "user_description": photo.get("user_description"),
            "tags": vision.get("tags") or [],
            "place": geo.get("place_name") or geo.get("city"),
            "taken_at": meta.get("taken_at"),
            "scene_type": vision.get("scene_type"),
            "status": photo.get("status"),
        }
