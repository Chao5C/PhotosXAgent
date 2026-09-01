from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.services.exif_service import make_thumbnail
from app.services.geo_service import geocode_photo_from_metadata
from photosx.agents.vision_agent import AI_CAPTION_FALLBACK
from app.services.photo_pipeline import PhotoPipeline
from app.utils.serialize import parse_object_id, serialize, utcnow

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


class PhotoService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.pipeline = PhotoPipeline(db)

    def _user_dir(self, user_id: str) -> Path:
        path = settings.upload_path / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_upload(self, user_id: str, upload: UploadFile) -> dict:
        suffix = Path(upload.filename or "photo.jpg").suffix.lower() or ".jpg"
        if suffix not in ALLOWED_EXT:
            raise ValueError("仅支持 jpg / png / webp / heic 图片")

        photo_id = str(ObjectId())
        filename = upload.filename or f"{photo_id}{suffix}"
        dest = self._user_dir(user_id) / f"{photo_id}{suffix}"
        content = await upload.read()
        if len(content) > settings.MAX_UPLOAD_SIZE:
            raise ValueError("文件过大")
        dest.write_bytes(content)

        thumb = self._user_dir(user_id) / f"{photo_id}_thumb.jpg"
        try:
            make_thumbnail(dest, thumb)
        except Exception as exc:
            logger.warning("thumbnail failed: %s", exc)
            thumb = dest

        now = utcnow()
        doc = {
            "_id": ObjectId(photo_id),
            "user_id": user_id,
            "filename": filename,
            "content_type": upload.content_type,
            "file_path": str(dest),
            "thumb_path": str(thumb),
            "status": "pending",
            "metadata": {},
            "vision": {},
            "geo": {},
            "created_at": now,
            "updated_at": now,
        }
        await self.db.photos.insert_one(doc)
        asyncio.create_task(self._safe_process(user_id, photo_id, str(dest)))
        return serialize(doc)

    async def _safe_process(self, user_id: str, photo_id: str, file_path: str) -> None:
        try:
            await self.pipeline.process_photo(user_id, photo_id, file_path)
        except Exception as exc:
            logger.exception("photo analysis failed: %s", photo_id)
            try:
                oid = parse_object_id(photo_id, field="photo_id")
            except ValueError:
                return
            await self.db.photos.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "failed",
                        "parse_error": str(exc)[:500],
                        "updated_at": utcnow(),
                    }
                },
            )

    async def reanalyze(self, user_id: str, photo_id: str) -> Optional[dict]:
        try:
            oid = parse_object_id(photo_id, field="photo_id")
        except ValueError:
            return None
        doc = await self.db.photos.find_one(
            {"_id": oid, "user_id": user_id, "status": {"$ne": "deleted"}}
        )
        if not doc:
            return None
        if doc.get("status") == "analyzing":
            return serialize(doc)
        await self.db.photos.update_one(
            {"_id": oid},
            {"$set": {"status": "pending", "parse_error": None, "updated_at": utcnow()}},
        )
        asyncio.create_task(self._safe_process(user_id, str(oid), doc["file_path"]))
        return await self.get_photo(user_id, str(oid))

    async def reanalyze_ids(self, user_id: str, photo_ids: list[str]) -> dict:
        queued: list[str] = []
        skipped = 0
        for raw_id in photo_ids or []:
            try:
                oid = parse_object_id(raw_id, field="photo_id")
            except ValueError:
                skipped += 1
                continue
            doc = await self.db.photos.find_one(
                {"_id": oid, "user_id": user_id, "status": {"$ne": "deleted"}}
            )
            if not doc:
                skipped += 1
                continue
            if doc.get("status") == "analyzing":
                skipped += 1
                continue
            photo_id = str(oid)
            await self.db.photos.update_one(
                {"_id": oid},
                {"$set": {"status": "pending", "parse_error": None, "updated_at": utcnow()}},
            )
            asyncio.create_task(self._safe_process(user_id, photo_id, doc["file_path"]))
            queued.append(photo_id)
        analyzing = await self.db.photos.count_documents({"user_id": user_id, "status": "analyzing"})
        return {"queued": len(queued), "photo_ids": queued, "skipped": skipped, "skipped_analyzing": analyzing}

    async def reanalyze_batch(
        self,
        user_id: str,
        *,
        include_pending: bool = True,
        include_failed: bool = True,
        include_bad_caption: bool = True,
    ) -> dict:
        filters: list[dict] = []
        if include_pending:
            filters.append({"status": "pending"})
        if include_failed:
            filters.append({"status": "failed"})
        if include_bad_caption:
            filters.append(
                {
                    "status": "ready",
                    "$or": [
                        {"vision.source": "fallback"},
                        {"vision.caption": AI_CAPTION_FALLBACK},
                        {"vision.caption": ""},
                    ],
                }
            )
        if not filters:
            return {"queued": 0, "photo_ids": [], "skipped_analyzing": 0}

        cursor = self.db.photos.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}, "$or": filters},
            {"_id": 1, "file_path": 1, "status": 1},
        )
        queued: list[str] = []
        seen: set[str] = set()
        async for doc in cursor:
            photo_id = str(doc["_id"])
            if photo_id in seen:
                continue
            seen.add(photo_id)
            await self.db.photos.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "pending", "parse_error": None, "updated_at": utcnow()}},
            )
            asyncio.create_task(self._safe_process(user_id, photo_id, doc["file_path"]))
            queued.append(photo_id)

        analyzing = await self.db.photos.count_documents({"user_id": user_id, "status": "analyzing"})
        return {"queued": len(queued), "photo_ids": queued, "skipped_analyzing": analyzing}

    async def get_parse_queue(self, user_id: str, limit: int = 30) -> dict:
        base = {"user_id": user_id, "status": {"$ne": "deleted"}}
        counts = {
            "pending": await self.db.photos.count_documents({**base, "status": "pending"}),
            "analyzing": await self.db.photos.count_documents({**base, "status": "analyzing"}),
            "failed": await self.db.photos.count_documents({**base, "status": "failed"}),
            "ready": await self.db.photos.count_documents({**base, "status": "ready"}),
        }
        active_filter = {**base, "status": {"$in": ["pending", "analyzing", "failed"]}}
        cursor = (
            self.db.photos.find(active_filter, {"filename": 1, "status": 1, "parse_error": 1, "updated_at": 1, "vision.caption": 1, "user_description": 1})
            .sort([("updated_at", -1)])
            .limit(limit)
        )
        items = []
        async for doc in cursor:
            row = serialize(doc) or {}
            from app.services.rag_service import photo_brief_caption

            row["caption"] = photo_brief_caption(row)
            items.append(row)
        return {
            "counts": counts,
            "active": counts["pending"] + counts["analyzing"] + counts["failed"],
            "items": items,
        }

    async def regeocode_batch(self, user_id: str) -> dict:
        """Refresh geo.place_* from GPS via Gaode/Nominatim (no LLM)."""
        from app.services.rag_service import RagService

        rag = RagService(self.db)
        cursor = self.db.photos.find(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "metadata.lat": {"$ne": None},
                "metadata.lng": {"$ne": None},
            }
        )
        updated = 0
        async for doc in cursor:
            meta = doc.get("metadata") or {}
            lat, lng = meta.get("lat"), meta.get("lng")
            if lat is None or lng is None:
                continue
            geo = await geocode_photo_from_metadata(meta)
            old_geo = dict(doc.get("geo") or {})
            if old_geo.get("weather"):
                geo["weather"] = old_geo["weather"]
            if old_geo.get("distance_from_home_km") is not None:
                geo["distance_from_home_km"] = old_geo["distance_from_home_km"]
            await self.db.photos.update_one(
                {"_id": doc["_id"]},
                {"$set": {"geo": geo, "updated_at": utcnow()}},
            )
            fresh = serialize(await self.db.photos.find_one({"_id": doc["_id"]}))
            if fresh:
                await rag.index_photo(user_id, fresh)
            updated += 1
        return {"updated": updated}

    async def list_photos(
        self,
        user_id: str,
        tag: Optional[str] = None,
        scene: Optional[str] = None,
        q: Optional[str] = None,
        skip: int = 0,
        limit: int = 40,
    ) -> dict:
        filters: dict = {"user_id": user_id, "status": {"$ne": "deleted"}}
        if tag:
            filters["vision.tags"] = tag
        if scene:
            filters["vision.scene_type"] = scene
        if q:
            filters["$or"] = [
                {"filename": {"$regex": q, "$options": "i"}},
                {"vision.caption": {"$regex": q, "$options": "i"}},
                {"vision.tags": {"$regex": q, "$options": "i"}},
                {"geo.place_name": {"$regex": q, "$options": "i"}},
                {"vision.long_description": {"$regex": q, "$options": "i"}},
                {"user_long_description": {"$regex": q, "$options": "i"}},
            ]
        total = await self.db.photos.count_documents(filters)
        cursor = self.db.photos.find(filters).sort("created_at", -1).skip(skip).limit(limit)
        items = [serialize(doc) for doc in await cursor.to_list(limit)]
        return {"items": items, "total": total}

    async def get_photo(self, user_id: str, photo_id: str) -> Optional[dict]:
        try:
            oid = parse_object_id(photo_id, field="photo_id")
        except ValueError:
            return None
        doc = await self.db.photos.find_one({"_id": oid, "user_id": user_id})
        return serialize(doc)

    async def update_description(self, user_id: str, photo_id: str, payload: dict) -> Optional[dict]:
        try:
            oid = parse_object_id(photo_id, field="photo_id")
        except ValueError:
            return None
        doc = await self.db.photos.find_one({"_id": oid, "user_id": user_id})
        if not doc:
            return None
        updates: dict = {"updated_at": utcnow()}
        if "user_description" in payload and payload["user_description"] is not None:
            updates["user_description"] = payload["user_description"]
        if "user_long_description" in payload and payload["user_long_description"] is not None:
            updates["user_long_description"] = payload["user_long_description"]
        vision = dict(doc.get("vision") or {})
        if payload.get("tags") is not None:
            vision["tags"] = payload["tags"]
            updates["vision"] = vision
        await self.db.photos.update_one({"_id": oid}, {"$set": updates})
        fresh = await self.get_photo(user_id, str(oid))
        if fresh:
            from app.services.rag_service import RagService

            await RagService(self.db).index_photo(user_id, fresh)
        return fresh

    async def delete_photo(self, user_id: str, photo_id: str) -> bool:
        try:
            oid = parse_object_id(photo_id, field="photo_id")
        except ValueError:
            return False
        result = await self.db.photos.update_one(
            {"_id": oid, "user_id": user_id},
            {"$set": {"status": "deleted", "updated_at": utcnow()}},
        )
        await self.db.albums.update_many({"user_id": user_id}, {"$pull": {"photo_ids": str(oid)}})
        return result.modified_count > 0

    async def delete_batch(self, user_id: str, photo_ids: list[str]) -> dict:
        deleted = 0
        skipped = 0
        removed_ids: list[str] = []
        for raw_id in photo_ids or []:
            try:
                oid = parse_object_id(raw_id, field="photo_id")
            except ValueError:
                skipped += 1
                continue
            result = await self.db.photos.update_one(
                {"_id": oid, "user_id": user_id},
                {"$set": {"status": "deleted", "updated_at": utcnow()}},
            )
            if result.modified_count:
                pid = str(oid)
                removed_ids.append(pid)
                deleted += 1
            else:
                skipped += 1
        if removed_ids:
            await self.db.albums.update_many(
                {"user_id": user_id},
                {"$pull": {"photo_ids": {"$in": removed_ids}}},
            )
        return {"deleted": deleted, "photo_ids": removed_ids, "skipped": skipped}

    async def stats(self, user_id: str) -> dict:
        total = await self.db.photos.count_documents({"user_id": user_id, "status": {"$ne": "deleted"}})
        ready = await self.db.photos.count_documents({"user_id": user_id, "status": "ready"})
        albums = await self.db.albums.count_documents({"user_id": user_id})
        recs = await self.db.recommendations.count_documents({"user_id": user_id, "read": False})
        geo_count = await self.db.photos.count_documents(
            {"user_id": user_id, "metadata.lat": {"$ne": None}}
        )
        return {
            "photos": total,
            "analyzed": ready,
            "albums": albums,
            "unread_recommendations": recs,
            "with_gps": geo_count,
        }
