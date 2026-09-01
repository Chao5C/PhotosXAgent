from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.response import ok
from app.services.studio_service import StudioService
from photosx.studio.skill_loader import resolve_skill_file, skills_root

router = APIRouter(prefix="/api/studio", tags=["studio"])


def _svc(user) -> StudioService:
    return StudioService(str(user["_id"]))


class TopicCreate(BaseModel):
    title: str
    seed: str = ""


class ContentUpdate(BaseModel):
    content_md: str


class ResearchIn(BaseModel):
    query: str | None = None


class DeriveIn(BaseModel):
    force: bool = False


class ProduceIn(BaseModel):
    force: bool = False


class PipelineIn(BaseModel):
    stages: list[str] = Field(default_factory=lambda: ["research", "derive", "produce"])


@router.get("/topics")
async def list_topics(user=Depends(get_current_user)):
    return ok(_svc(user).list_topics())


@router.post("/topics")
async def create_topic(payload: TopicCreate, user=Depends(get_current_user)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    return ok(_svc(user).create_topic(payload.title.strip(), payload.seed), "已创建选题")


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: str, user=Depends(get_current_user)):
    try:
        return ok(_svc(user).get_topic(topic_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/topics/{topic_id}/content")
async def update_content(topic_id: str, payload: ContentUpdate, user=Depends(get_current_user)):
    try:
        return ok(_svc(user).update_content(topic_id, payload.content_md), "已更新 content.md，下游标记为 stale")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str, user=Depends(get_current_user)):
    try:
        _svc(user).delete_topic(topic_id)
        return ok({"deleted": True})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/topics/{topic_id}/research")
async def research(topic_id: str, payload: ResearchIn | None = None, user=Depends(get_current_user)):
    try:
        return ok(await _svc(user).research(topic_id, (payload.query if payload else None)), "调研完成，已写入 content.md")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None


@router.post("/topics/{topic_id}/derive")
async def derive(topic_id: str, payload: DeriveIn | None = None, user=Depends(get_current_user)):
    try:
        force = bool(payload.force) if payload else False
        return ok(await _svc(user).derive(topic_id, force=force), "已派生稿件")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None


@router.post("/topics/{topic_id}/produce")
async def produce(topic_id: str, payload: ProduceIn | None = None, user=Depends(get_current_user)):
    try:
        force = bool(payload.force) if payload else False
        return ok(await _svc(user).produce(topic_id, force=force), "制作层已更新（成片可能仍为占位）")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None


@router.post("/topics/{topic_id}/pipeline")
async def pipeline(topic_id: str, payload: PipelineIn | None = None, user=Depends(get_current_user)):
    try:
        stages = payload.stages if payload else ["research", "derive", "produce"]
        return ok(await _svc(user).run_pipeline(topic_id, stages), "流水线已执行")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="选题不存在") from None


@router.get("/topics/{topic_id}/file")
async def read_file(topic_id: str, path: str = Query(...), user=Depends(get_current_user)):
    try:
        return ok(_svc(user).read_file(topic_id, path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/topics/{topic_id}/deck")
async def deck_html(topic_id: str, user=Depends(get_current_user)):
    try:
        data = _svc(user).read_file(topic_id, "scripts/deck.html")
        return HTMLResponse(data["content"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="尚未生成 HTML-PPT，请先派生") from None


@router.get("/skill-assets/{skill_name}/{asset_path:path}")
async def skill_assets(skill_name: str, asset_path: str):
    """Serve vendored GitHub skill static files (html-ppt themes/runtime, etc.)."""
    allowed = {"html-ppt", "video-podcast-maker", "humanizer"}
    if skill_name not in allowed:
        raise HTTPException(status_code=404, detail="unknown skill")
    path = resolve_skill_file(skill_name, asset_path)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)


@router.get("/skills")
async def list_skills(user=Depends(get_current_user)):
    root = skills_root()
    items = []
    for name in ("humanizer", "html-ppt", "video-podcast-maker"):
        d = root / name
        origin = ""
        if (d / "ORIGIN.txt").exists():
            origin = (d / "ORIGIN.txt").read_text(encoding="utf-8", errors="ignore").strip()
        items.append(
            {
                "name": name,
                "installed": (d / "SKILL.md").exists(),
                "origin": origin,
            }
        )
    return ok(items)
