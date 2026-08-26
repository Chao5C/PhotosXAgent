from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.serialize import serialize


class AlbumService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def list_albums(self, user_id: str) -> list[dict]:
        cursor = self.db.albums.find({"user_id": user_id}).sort("updated_at", -1)
        albums = []
        async for doc in cursor:
            item = serialize(doc)
            ids = item.get("photo_ids") or []
            item["count"] = len(ids)
            cover = None
            if ids:
                photo = await self.db.photos.find_one({"_id": ObjectId(ids[-1])})
                if photo:
                    cover = str(photo["_id"])
            item["cover_id"] = cover
            albums.append(item)
        return albums

    async def get_album(self, user_id: str, album_id: str) -> Optional[dict]:
        doc = await self.db.albums.find_one({"_id": ObjectId(album_id), "user_id": user_id})
        if not doc:
            return None
        album = serialize(doc)
        photos = []
        for pid in album.get("photo_ids") or []:
            photo = await self.db.photos.find_one({"_id": ObjectId(pid), "user_id": user_id})
            if photo and photo.get("status") != "deleted":
                photos.append(serialize(photo))
        album["photos"] = photos
        album["count"] = len(photos)
        return album
