from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.geo_service import resolve_photo_place
from app.utils.serialize import serialize


class JourneyService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def build_journey(self, user_id: str) -> dict:
        cursor = self.db.photos.find(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "metadata.lat": {"$ne": None},
                "metadata.lng": {"$ne": None},
            }
        )
        points = []
        async for doc in cursor:
            item = serialize(doc)
            meta = item.get("metadata") or {}
            geo = item.get("geo") or {}
            taken = meta.get("taken_at") or item.get("created_at")
            points.append(
                {
                    "id": item["id"],
                    "filename": item.get("filename"),
                    "taken_at": taken,
                    "lat": meta.get("lat"),
                    "lng": meta.get("lng"),
                    "place": resolve_photo_place(geo, meta),
                    "city": geo.get("city"),
                    "caption": (item.get("vision") or {}).get("caption"),
                    "tags": (item.get("vision") or {}).get("tags") or [],
                }
            )

        def sort_key(p):
            value = p.get("taken_at") or ""
            return str(value)

        points.sort(key=sort_key)
        segments = []
        for prev, curr in zip(points, points[1:]):
            segments.append(
                {
                    "from_id": prev["id"],
                    "to_id": curr["id"],
                    "from_place": prev.get("place"),
                    "to_place": curr.get("place"),
                    "start": prev.get("taken_at"),
                    "end": curr.get("taken_at"),
                }
            )
        return {"points": points, "segments": segments, "count": len(points)}
