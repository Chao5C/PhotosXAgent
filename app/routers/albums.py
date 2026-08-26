from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.album_service import AlbumService

router = APIRouter(prefix="/api/albums", tags=["albums"])


@router.get("")
async def list_albums(user=Depends(get_current_user)):
    return ok(await AlbumService(get_db()).list_albums(str(user["_id"])))


@router.get("/{album_id}")
async def get_album(album_id: str, user=Depends(get_current_user)):
    album = await AlbumService(get_db()).get_album(str(user["_id"]), album_id)
    if not album:
        raise HTTPException(status_code=404, detail="相册不存在")
    return ok(album)
