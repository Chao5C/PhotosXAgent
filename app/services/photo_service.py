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
from app.services.photo_pipeline import PhotoPipeline
from app.utils.serialize import serialize, utcnow

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
        except Exception:
            logger.exception("photo analysis failed: %s", photo_id)
            await self.db.photos.update_one(
                {"_id": ObjectId(photo_id)},
                {"$set": {"status": "failed", "updated_at": utcnow()}},
            )

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
                {"geo.city": {"$regex": q, "$options": "i"}},
            ]
        total = await self.db.photos.count_documents(filters)
        cursor = self.db.photos.find(filters).sort("created_at", -1).skip(skip).limit(limit)
        items = [serialize(doc) for doc in await cursor.to_list(limit)]
        return {"items": items, "total": total}

    async def get_photo(self, user_id: str, photo_id: str) -> Optional[dict]:
        doc = await self.db.photos.find_one({"_id": ObjectId(photo_id), "user_id": user_id})
        return serialize(doc)

    async def delete_photo(self, user_id: str, photo_id: str) -> bool:
        result = await self.db.photos.update_one(
            {"_id": ObjectId(photo_id), "user_id": user_id},
            {"$set": {"status": "deleted", "updated_at": utcnow()}},
        )
        await self.db.albums.update_many({"user_id": user_id}, {"$pull": {"photo_ids": photo_id}})
        return result.modified_count > 0

    async def reanalyze(self, user_id: str, photo_id: str) -> Optional[dict]:
        doc = await self.db.photos.find_one({"_id": ObjectId(photo_id), "user_id": user_id})
        if not doc:
            return None
        asyncio.create_task(self._safe_process(user_id, photo_id, doc["file_path"]))
        return serialize(doc)

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
