from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.geo_service import enrich_geo, fetch_weather, geocode_photo_from_metadata, haversine_km, resolve_photo_place, reverse_geocode
from app.utils.serialize import is_valid_object_id, parse_object_id, serialize, utcnow
from photosx.agents.vision_agent import AI_CAPTION_FALLBACK, run_vision_agent

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
            {"_id": parse_object_id(photo_id, field="photo_id")},
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

        geo = enrich_geo(metadata, geo)

        now = utcnow()
        vision_ok = (vision.get("source") or "") != "fallback" and bool((vision.get("caption") or "").strip()) and (
            vision.get("caption") or ""
        ) != AI_CAPTION_FALLBACK
        status = "ready" if vision_ok else "failed"
        parse_error = None if vision_ok else (vision.get("error") or AI_CAPTION_FALLBACK)
        await self.db.photos.update_one(
            {"_id": parse_object_id(photo_id, field="photo_id")},
            {
                "$set": {
                    "metadata": metadata,
                    "vision": vision,
                    "geo": geo,
                    "status": status,
                    "parse_error": parse_error,
                    "analyzed_at": now if vision_ok else None,
                    "updated_at": now,
                }
            },
        )

        if not vision_ok:
            return {
                "photo_id": photo_id,
                "metadata": metadata,
                "vision": vision,
                "geo": geo,
                "albums": [],
                "analysis": None,
                "failed": True,
            }

        albums = await self._assign_albums(user_id, photo_id, vision, geo, metadata)
        photo_doc = await self.db.photos.find_one({"_id": parse_object_id(photo_id, field="photo_id")})
        from app.services.analysis_service import AnalysisService
        from app.services.rag_service import RagService

        compact = serialize(photo_doc) or {}
        await RagService(self.db).index_photo(user_id, compact)
        analysis_svc = AnalysisService(self.db)
        analysis = None
        try:
            analysis = await analysis_svc.analyze(user_id, [photo_id], request_text="pipeline")
            if (analysis or {}).get("status") == "triggered":
                await analysis_svc.push(user_id, analysis_id=analysis.get("id"), force=False)
        except Exception as exc:
            logger.warning("post-parse analysis push skipped for %s: %s", photo_id, exc)

        return {
            "photo_id": photo_id,
            "metadata": metadata,
            "vision": vision,
            "geo": geo,
            "albums": albums,
            "analysis": analysis,
        }

    async def _home_centroid(self, user_id: str, exclude_id: str) -> Optional[tuple[float, float]]:
        filters: dict = {
            "user_id": user_id,
            "metadata.lat": {"$ne": None},
            "metadata.lng": {"$ne": None},
        }
        if is_valid_object_id(exclude_id):
            filters["_id"] = {"$ne": parse_object_id(exclude_id, field="photo_id")}
        cursor = self.db.photos.find(
            filters,
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

        place = resolve_photo_place(geo, metadata)
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
