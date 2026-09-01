from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.poster_service import PosterService
from app.utils.serialize import is_valid_object_id

router = APIRouter(prefix="/api/posters", tags=["posters"])


@router.get("")
async def list_posters(user=Depends(get_current_user)):
    db = get_db()
    items = await PosterService(str(user["_id"])).list_posters(db)
    return ok({"items": items, "total": len(items)})


@router.get("/{poster_id}/file")
async def get_poster_file(poster_id: str, user=Depends(get_current_user)):
    if not is_valid_object_id(poster_id):
        raise HTTPException(status_code=400, detail="无效的海报 ID")
    path = await PosterService(str(user["_id"])).get_file_path(get_db(), poster_id)
    if not path:
        raise HTTPException(status_code=404, detail="海报不存在")
    return FileResponse(path, media_type="image/png", filename=f"poster-{poster_id}.png")


@router.delete("/{poster_id}")
async def delete_poster(poster_id: str, user=Depends(get_current_user)):
    if not is_valid_object_id(poster_id):
        raise HTTPException(status_code=400, detail="无效的海报 ID")
    ok_deleted = await PosterService(str(user["_id"])).delete_poster(get_db(), poster_id)
    if not ok_deleted:
        raise HTTPException(status_code=404, detail="海报不存在")
    return ok({"deleted": True})
