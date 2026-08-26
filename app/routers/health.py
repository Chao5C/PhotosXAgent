from fastapi import APIRouter

from app.core.config import settings
from app.core.response import ok

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    return ok({"status": "ok", "name": "PhotosXAgent", "version": "0.1.0", "timezone": settings.TIMEZONE})
