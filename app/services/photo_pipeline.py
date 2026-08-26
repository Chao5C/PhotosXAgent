from __future__ import annotations

import logging
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.services.geo_service import fetch_weather, haversine_km, reverse_geocode
from app.utils.serialize import serialize, utcnow
from photosx.agents.recommend_agent import run_recommend_agent
from photosx.agents.vision_agent import run_vision_agent

logger = logging.getLogger(__name__)

SCENE_ALBUMS = {
    "group": ("合照", "group"),
    "pet": ("宠物照", "pet"),
    "scenery": ("风景照", "scenery"),
    "food": ("美食", "food"),
    "architecture": ("建筑", "architecture"),
    "other": ("未分类", "other"),
}


class PhotoPipeline:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def process_photo(self, user_id: str, photo_id: str, file_path: str) -> dict:
        await self.db.photos.update_one(
            {"_id": ObjectId(photo_id)},
            {"$set": {"status": "analyzing", "updated_at": utcnow()}},
        )

        state = await run_vision_agent(
            {"user_id": user_id, "photo_id": photo_id, "file_path": file_path}
        )
        metadata = state.get("metadata") or {}
        vision = state.get("vision") or {}
        geo = {}

        lat, lng = metadata.get("lat"), metadata.get("lng")
        if lat is not None and lng is not None:
            geo = await reverse_geocode(float(lat), float(lng))
            home = await self._home_centroid(user_id, exclude_id=photo_id)
            if home:
                distance = haversine_km(home, (float(lat), float(lng)))
                geo["distance_from_home_km"] = round(distance, 2)
                geo["home_lat"], geo["home_lng"] = home
            geo["weather"] = await fetch_weather(float(lat), float(lng))

        now = utcnow()
        await self.db.photos.update_one(
            {"_id": ObjectId(photo_id)},
            {
                "$set": {
                    "metadata": metadata,
                    "vision": vision,
                    "geo": geo,
                    "status": "ready",
                    "analyzed_at": now,
                    "updated_at": now,
                }
            },
        )

        albums = await self._assign_albums(user_id, photo_id, vision, geo, metadata)
        recommendation = None
        distance = (geo or {}).get("distance_from_home_km")
        if distance is not None and distance >= settings.DISTANCE_THRESHOLD_KM:
            rec_state = await run_recommend_agent(
                {**state, "geo": geo, "vision": vision}
            )
            recommendation = rec_state.get("recommendation")
            if recommendation:
                rec_doc = {
                    "user_id": user_id,
                    "photo_id": photo_id,
                    **recommendation,
                    "read": False,
                    "created_at": now,
                }
                inserted = await self.db.recommendations.insert_one(rec_doc)
                recommendation["id"] = str(inserted.inserted_id)

        return {
            "photo_id": photo_id,
            "metadata": metadata,
            "vision": vision,
            "geo": geo,
            "albums": albums,
            "recommendation": recommendation,
        }

    async def _home_centroid(self, user_id: str, exclude_id: str) -> Optional[tuple[float, float]]:
        cursor = self.db.photos.find(
            {
                "user_id": user_id,
                "_id": {"$ne": ObjectId(exclude_id)},
                "metadata.lat": {"$ne": None},
                "metadata.lng": {"$ne": None},
            },
            {"metadata.lat": 1, "metadata.lng": 1},
        )
        lats, lngs = [], []
        async for doc in cursor:
            meta = doc.get("metadata") or {}
            if meta.get("lat") is not None and meta.get("lng") is not None:
                lats.append(float(meta["lat"]))
                lngs.append(float(meta["lng"]))
        if len(lats) < 3:
            return None
        return (sum(lats) / len(lats), sum(lngs) / len(lngs))

    async def _assign_albums(self, user_id: str, photo_id: str, vision: dict, geo: dict, metadata: dict) -> list[str]:
        names = []
        scene = (vision or {}).get("scene_type")
        if scene in SCENE_ALBUMS:
            title, kind = SCENE_ALBUMS[scene]
            await self._add_to_album(user_id, title, kind, photo_id)
            names.append(title)

        tags = (vision or {}).get("tags") or []
        if "合照" in tags and "合照" not in names:
            await self._add_to_album(user_id, "合照", "group", photo_id)
            names.append("合照")
        people = int((vision or {}).get("people_count") or 0)
        if people >= 2 and "合照" not in names:
            await self._add_to_album(user_id, "合照", "group", photo_id)
            names.append("合照")

        place = (geo or {}).get("city") or (geo or {}).get("place_name")
        if place:
            title = f"{place}合集"
            await self._add_to_album(user_id, title, "location", photo_id, location=place)
            names.append(title)
        return names

    async def _add_to_album(self, user_id: str, name: str, kind: str, photo_id: str, location: str | None = None) -> None:
        now = utcnow()
        await self.db.albums.update_one(
            {"user_id": user_id, "name": name},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "name": name,
                    "kind": kind,
                    "location": location,
                    "created_at": now,
                },
                "$addToSet": {"photo_ids": photo_id},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
