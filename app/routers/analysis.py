from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalyzeIn(BaseModel):
    photo_ids: list[str] = Field(default_factory=list)
    request_text: str = ""


class PushIn(BaseModel):
    analysis_id: str | None = None
    photo_ids: list[str] = Field(default_factory=list)
    force: bool = False


def _svc() -> AnalysisService:
    return AnalysisService(get_db())


@router.post("/analyze")
async def analyze(payload: AnalyzeIn, user=Depends(get_current_user)):
    result = await _svc().analyze(str(user["_id"]), payload.photo_ids or None, payload.request_text)
    return ok(result, "已分析并入库")


@router.post("/push")
async def push(payload: PushIn, user=Depends(get_current_user)):
    result = await _svc().push(
        str(user["_id"]),
        analysis_id=payload.analysis_id,
        photo_ids=payload.photo_ids or None,
        force=payload.force,
    )
    return ok(result, "已处理推送")
