from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.llm_config_service import LLMConfigService
from photosx.llm.client import list_enabled_models, refresh_runtime

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _svc() -> LLMConfigService:
    return LLMConfigService(get_db())


class ProviderIn(BaseModel):
    name: str
    display_name: str
    description: str | None = None
    website: str | None = None
    api_doc_url: str | None = None
    default_base_url: str | None = None
    test_model: str | None = None
    api_key: str | None = None
    supported_features: list[str] = Field(default_factory=list)
    is_active: bool = True


class ToggleIn(BaseModel):
    is_active: bool | None = None
    enabled: bool | None = None


class CatalogIn(BaseModel):
    provider: str
    provider_name: str
    models: list[dict] = Field(default_factory=list)


class ModelIn(BaseModel):
    provider: str
    model_name: str
    model_display_name: str | None = None
    api_base: str | None = None
    max_tokens: int = 8000
    temperature: float = 0.2
    timeout: int = 120
    retry_times: int = 2
    enabled: bool = True
    capability_level: int | None = None
    suitable_roles: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    recommended_depths: list[str] = Field(default_factory=list)


@router.get("/providers")
async def list_providers(_user=Depends(get_current_user)):
    return ok(await _svc().list_providers())


@router.post("/providers")
async def add_provider(payload: ProviderIn, _user=Depends(get_current_user)):
    try:
        item = await _svc().upsert_provider(payload.model_dump(), is_new=True)
        await refresh_runtime()
        return ok(item, "已添加厂家")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/providers/{name}")
async def update_provider(name: str, payload: ProviderIn, _user=Depends(get_current_user)):
    data = payload.model_dump()
    data["name"] = name
    item = await _svc().upsert_provider(data, is_new=False)
    await refresh_runtime()
    return ok(item, "已更新厂家")


@router.post("/providers/{name}/toggle")
async def toggle_provider(name: str, payload: ToggleIn, _user=Depends(get_current_user)):
    try:
        item = await _svc().toggle_provider(name, bool(payload.is_active))
        await refresh_runtime()
        return ok(item)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/providers/{name}")
async def delete_provider(name: str, _user=Depends(get_current_user)):
    await _svc().delete_provider(name)
    await refresh_runtime()
    return ok({"deleted": True})


@router.post("/providers/{name}/test")
async def test_provider(name: str, _user=Depends(get_current_user)):
    try:
        return ok(await _svc().test_provider(name), "连接成功")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers/ollama/local-models")
async def list_ollama_local(_user=Depends(get_current_user)):
    try:
        return ok(await _svc().list_ollama_local())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/providers/ollama/sync")
async def sync_ollama(_user=Depends(get_current_user)):
    try:
        result = await _svc().sync_ollama_models()
        await refresh_runtime()
        return ok(result, f"已同步 {result['count']} 个本机 Ollama 模型")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalogs")
async def list_catalogs(_user=Depends(get_current_user)):
    return ok(await _svc().list_catalogs())


@router.post("/catalogs")
async def upsert_catalog(payload: CatalogIn, _user=Depends(get_current_user)):
    return ok(await _svc().upsert_catalog(payload.model_dump()), "已保存目录")


@router.delete("/catalogs/{provider}")
async def delete_catalog(provider: str, _user=Depends(get_current_user)):
    await _svc().delete_catalog(provider)
    return ok({"deleted": True})


@router.get("/models")
async def list_models(_user=Depends(get_current_user)):
    return ok(await _svc().list_models())


@router.post("/models")
async def upsert_model(payload: ModelIn, _user=Depends(get_current_user)):
    item = await _svc().upsert_model(payload.model_dump())
    await refresh_runtime()
    return ok(item, "已保存模型")


@router.post("/models/{provider}/{model_name}/toggle")
async def toggle_model(provider: str, model_name: str, payload: ToggleIn, _user=Depends(get_current_user)):
    try:
        item = await _svc().toggle_model(provider, model_name, bool(payload.enabled))
        await refresh_runtime()
        return ok(item)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/models/{provider}/{model_name}")
async def delete_model(provider: str, model_name: str, _user=Depends(get_current_user)):
    await _svc().delete_model(provider, model_name)
    await refresh_runtime()
    return ok({"deleted": True})


@router.post("/models/{provider}/{model_name}/test")
async def test_model(provider: str, model_name: str, _user=Depends(get_current_user)):
    try:
        return ok(await _svc().test_model(provider, model_name), "模型可用")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/enabled-models")
async def enabled_models(_user=Depends(get_current_user)):
    await refresh_runtime()
    return ok(list_enabled_models())


@router.post("/reload")
async def reload_llm(_user=Depends(get_current_user)):
    await _svc().ensure_defaults()
    await refresh_runtime()
    return ok({"reloaded": True}, "已重载 LLM 配置")
