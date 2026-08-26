from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/api/photos", tags=["photos"])


def _service():
    return PhotoService(get_db())


@router.post("/upload")
async def upload_photos(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    service = _service()
    items = []
    errors = []
    for upload in files:
        try:
            items.append(await service.save_upload(str(user["_id"]), upload))
        except Exception as exc:
            errors.append({"filename": upload.filename, "error": str(exc)})
    return ok({"items": items, "errors": errors})


@router.get("")
async def list_photos(
    tag: str | None = None,
    scene: str | None = None,
    q: str | None = None,
    skip: int = 0,
    limit: int = Query(default=40, le=100),
    user=Depends(get_current_user),
):
    return ok(await _service().list_photos(str(user["_id"]), tag, scene, q, skip, limit))


@router.get("/stats")
async def photo_stats(user=Depends(get_current_user)):
    return ok(await _service().stats(str(user["_id"])))


@router.get("/{photo_id}")
async def get_photo(photo_id: str, user=Depends(get_current_user)):
    photo = await _service().get_photo(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok(photo)


@router.post("/{photo_id}/analyze")
async def reanalyze(photo_id: str, user=Depends(get_current_user)):
    photo = await _service().reanalyze(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok(photo, "已重新提交解析")


@router.delete("/{photo_id}")
async def delete_photo(photo_id: str, user=Depends(get_current_user)):
    deleted = await _service().delete_photo(str(user["_id"]), photo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok({"deleted": True})


@router.get("/{photo_id}/file")
async def photo_file(photo_id: str, thumb: bool = False, user=Depends(get_current_user)):
    photo = await _service().get_photo(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    path = Path(photo["thumb_path"] if thumb and photo.get("thumb_path") else photo["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)
