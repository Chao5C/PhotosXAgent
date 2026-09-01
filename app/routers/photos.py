from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.photo_service import PhotoService
from app.utils.serialize import is_valid_object_id

router = APIRouter(prefix="/api/photos", tags=["photos"])


def _service():
    return PhotoService(get_db())


def _require_photo_id(photo_id: str) -> str:
    if not is_valid_object_id(photo_id):
        raise HTTPException(status_code=400, detail="无效的照片 ID")
    return photo_id


class PhotoPatch(BaseModel):
    tags: list[str] | None = None
    user_description: str | None = None
    user_long_description: str | None = None


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


@router.get("/parse-queue")
async def parse_queue(user=Depends(get_current_user)):
    return ok(await _service().get_parse_queue(str(user["_id"])))


class ReanalyzeBatchIn(BaseModel):
    include_pending: bool = True
    include_failed: bool = True


class PhotoIdsIn(BaseModel):
    photo_ids: list[str]


@router.post("/reanalyze-batch")
async def reanalyze_batch(payload: ReanalyzeBatchIn | None = None, user=Depends(get_current_user)):
    body = payload or ReanalyzeBatchIn()
    result = await _service().reanalyze_batch(
        str(user["_id"]),
        include_pending=body.include_pending,
        include_failed=body.include_failed,
    )
    return ok(result, f"已提交 {result['queued']} 张照片重新解析")


@router.post("/reanalyze-ids")
async def reanalyze_ids(payload: PhotoIdsIn, user=Depends(get_current_user)):
    ids = [pid for pid in payload.photo_ids if is_valid_object_id(pid)]
    if not ids:
        raise HTTPException(status_code=400, detail="请选择有效的照片")
    result = await _service().reanalyze_ids(str(user["_id"]), ids)
    return ok(result, f"已提交 {result['queued']} 张照片重新解析")


@router.post("/delete-batch")
async def delete_batch(payload: PhotoIdsIn, user=Depends(get_current_user)):
    ids = [pid for pid in payload.photo_ids if is_valid_object_id(pid)]
    if not ids:
        raise HTTPException(status_code=400, detail="请选择有效的照片")
    result = await _service().delete_batch(str(user["_id"]), ids)
    return ok(result, f"已删除 {result['deleted']} 张照片")


@router.post("/regeocode-batch")
async def regeocode_batch(user=Depends(get_current_user)):
    result = await _service().regeocode_batch(str(user["_id"]))
    return ok(result, f"已根据 GPS 刷新 {result['updated']} 张照片的地点")


@router.get("/stats")
async def photo_stats(user=Depends(get_current_user)):
    return ok(await _service().stats(str(user["_id"])))


@router.get("/{photo_id}")
async def get_photo(photo_id: str, user=Depends(get_current_user)):
    _require_photo_id(photo_id)
    photo = await _service().get_photo(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok(photo)


@router.patch("/{photo_id}")
async def patch_photo(photo_id: str, payload: PhotoPatch, user=Depends(get_current_user)):
    _require_photo_id(photo_id)
    photo = await _service().update_description(str(user["_id"]), photo_id, payload.model_dump(exclude_unset=True))
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok(photo, "已更新描述")


@router.post("/{photo_id}/analyze")
async def reanalyze(photo_id: str, user=Depends(get_current_user)):
    _require_photo_id(photo_id)
    photo = await _service().reanalyze(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok(photo, "已重新提交解析")


@router.delete("/{photo_id}")
async def delete_photo(photo_id: str, user=Depends(get_current_user)):
    _require_photo_id(photo_id)
    deleted = await _service().delete_photo(str(user["_id"]), photo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="照片不存在")
    return ok({"deleted": True})


@router.get("/{photo_id}/file")
async def photo_file(photo_id: str, thumb: bool = False, user=Depends(get_current_user)):
    _require_photo_id(photo_id)
    photo = await _service().get_photo(str(user["_id"]), photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    path = Path(photo["thumb_path"] if thumb and photo.get("thumb_path") else photo["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)
