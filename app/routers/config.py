from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from photosx.llm.client import llm_available, persist_agent_models, refresh_runtime

router = APIRouter(prefix="/api/config", tags=["config"])


class AgentBinding(BaseModel):
    provider: str = ""
    model_name: str = ""


class ConfigUpdate(BaseModel):
    llm_provider: str | None = None
    llm_vision_model: str | None = None
    llm_text_model: str | None = None
    distance_threshold_km: float | None = None
    agent_models: dict[str, AgentBinding] | None = None


def _normalize_agent_models(raw: dict | None) -> dict[str, dict]:
    defaults = {
        "agent1": {"provider": "", "model_name": ""},
        "agent2": {"provider": "", "model_name": ""},
        "agent3": {"provider": "", "model_name": ""},
    }
    for key, val in (raw or {}).items():
        if key in defaults and isinstance(val, dict):
            defaults[key] = {
                "provider": val.get("provider") or "",
                "model_name": val.get("model_name") or "",
            }
    return defaults


@router.get("")
async def get_config(_user=Depends(get_current_user)):
    db = get_db()
    stored = await db.system_config.find_one({"key": "app"}) or {}
    values = stored.get("values") or {}
    return ok(
        {
            "llm_provider": values.get("llm_provider") or settings.LLM_PROVIDER,
            "llm_vision_model": values.get("llm_vision_model") or settings.LLM_VISION_MODEL,
            "llm_text_model": values.get("llm_text_model") or settings.LLM_TEXT_MODEL,
            "distance_threshold_km": values.get("distance_threshold_km") or settings.DISTANCE_THRESHOLD_KM,
            "llm_available": llm_available(),
            "agent_models": _normalize_agent_models(values.get("agent_models")),
        }
    )


@router.put("")
async def update_config(payload: ConfigUpdate, _user=Depends(get_current_user)):
    db = get_db()
    data = payload.model_dump(exclude_none=True)
    agent_models = data.pop("agent_models", None)
    if "distance_threshold_km" in data:
        settings.DISTANCE_THRESHOLD_KM = float(data["distance_threshold_km"])
    if "llm_provider" in data:
        settings.LLM_PROVIDER = data["llm_provider"]
    if "llm_vision_model" in data:
        settings.LLM_VISION_MODEL = data["llm_vision_model"]
    if "llm_text_model" in data:
        settings.LLM_TEXT_MODEL = data["llm_text_model"]
    set_doc = {f"values.{k}": v for k, v in data.items()}
    if set_doc:
        await db.system_config.update_one({"key": "app"}, {"$set": set_doc}, upsert=True)
    if agent_models is not None:
        await persist_agent_models(agent_models)
    await refresh_runtime()
    return await get_config(_user)
