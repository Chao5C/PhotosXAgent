from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

PROVIDER_CONFIG = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "deepseek": (settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "volcengine": (settings.VOLCENGINE_BASE_URL or "https://ark.cn-beijing.volces.com/api/v3", "VOLCENGINE_API_KEY"),
    "volcengine_coding": (
        settings.VOLCENGINE_CODING_BASE_URL or "https://ark.cn-beijing.volces.com/api/coding/v3",
        "VOLCENGINE_CODING_API_KEY",
    ),
    "ollama": (settings.OLLAMA_BASE_URL or "http://localhost:11434/v1", None),
    "custom_openai": (None, "CUSTOM_OPENAI_API_KEY"),
}

_runtime: dict[str, Any] = {"providers": {}, "models": [], "agent_models": {}}


async def refresh_runtime() -> None:
    from app.core.database import get_db
    from app.services.llm_config_service import env_api_key

    try:
        db = get_db()
    except Exception:
        return
    providers = {}
    async for doc in db.llm_providers.find():
        name = doc.get("name")
        if not name:
            continue
        api_key = (doc.get("api_key") or "").strip() or env_api_key(name)
        if name == "volcengine_coding" and not api_key:
            sibling = await db.llm_providers.find_one({"name": "volcengine"})
            if sibling and sibling.get("is_active"):
                api_key = ((sibling or {}).get("api_key") or "").strip() or env_api_key("volcengine")
        if name == "ollama":
            api_key = api_key or "ollama"
        base_url = (doc.get("default_base_url") or "").rstrip("/")
        if name == "ollama":
            base_url = (settings.OLLAMA_BASE_URL or base_url or "http://localhost:11434/v1").rstrip("/")
        providers[name] = {
            "is_active": bool(doc.get("is_active")),
            "base_url": base_url,
            "api_key": api_key,
            "display_name": doc.get("display_name") or name,
        }
    models = [doc async for doc in db.llm_models.find({"enabled": True})]
    stored = await db.system_config.find_one({"key": "app"}) or {}
    agent_models = ((stored.get("values") or {}).get("agent_models")) or {}
    _runtime["providers"] = providers
    _runtime["models"] = models
    _runtime["agent_models"] = agent_models
    logger.info(
        "LLM runtime refreshed: %s providers, %s models, agents=%s",
        len(providers),
        len(models),
        list(agent_models.keys()),
    )


def llm_available() -> bool:
    for provider in (_runtime.get("providers") or {}).values():
        if provider.get("is_active") and provider.get("api_key"):
            return True
    provider = (settings.LLM_PROVIDER or "qwen").lower()
    return bool(_api_key_for(provider) or settings.CUSTOM_OPENAI_API_KEY)


def _api_key_for(provider: str) -> str:
    cached = (_runtime.get("providers") or {}).get(provider) or {}
    if cached.get("api_key"):
        return cached["api_key"]
    _, env_name = PROVIDER_CONFIG.get(provider, (None, "OPENAI_API_KEY"))
    if not env_name:
        return "ollama" if provider == "ollama" else ""
    mapped = {
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "DASHSCOPE_API_KEY": settings.DASHSCOPE_API_KEY,
        "DEEPSEEK_API_KEY": settings.DEEPSEEK_API_KEY,
        "CUSTOM_OPENAI_API_KEY": settings.CUSTOM_OPENAI_API_KEY,
        "VOLCENGINE_API_KEY": settings.VOLCENGINE_API_KEY or os.environ.get("VOLCENGINE_API_KEY", ""),
        "VOLCENGINE_CODING_API_KEY": settings.VOLCENGINE_CODING_API_KEY
        or os.environ.get("VOLCENGINE_CODING_API_KEY", "")
        or settings.VOLCENGINE_API_KEY
        or os.environ.get("VOLCENGINE_API_KEY", ""),
    }
    return mapped.get(env_name, "") or os.environ.get(env_name or "", "")


def _pick_model(prefer_vision: bool) -> tuple[str, str, Optional[str]]:
    models = _runtime.get("models") or []
    providers = _runtime.get("providers") or {}

    def usable(doc: dict) -> bool:
        provider = providers.get(doc.get("provider") or "")
        return bool(provider and provider.get("is_active") and provider.get("api_key"))

    vision = [m for m in models if usable(m) and ("vision" in (m.get("features") or []) or "vision" in (m.get("suitable_roles") or []))]
    text = [m for m in models if usable(m) and m not in vision]
    chosen = (vision if prefer_vision and vision else None) or (text if not prefer_vision and text else None) or vision or text
    if chosen:
        doc = chosen[0]
        provider_name = doc.get("provider") or settings.LLM_PROVIDER
        info = providers.get(provider_name) or {}
        return provider_name, doc.get("model_name") or settings.LLM_TEXT_MODEL, info.get("base_url")
    provider_name = (settings.LLM_PROVIDER or "qwen").lower()
    model = settings.LLM_VISION_MODEL if prefer_vision else settings.LLM_TEXT_MODEL
    default_url, _ = PROVIDER_CONFIG.get(provider_name, PROVIDER_CONFIG["openai"])
    return provider_name, model, settings.CUSTOM_OPENAI_BASE_URL or default_url


def create_chat_model(
    model: Optional[str] = None,
    temperature: float = 0.2,
    vision: bool = False,
    provider: Optional[str] = None,
) -> ChatOpenAI:
    provider_name, picked_model, base_url = _pick_model(prefer_vision=vision)
    if model:
        picked_model = model
        matches = [
            doc
            for doc in (_runtime.get("models") or [])
            if doc.get("model_name") == model and (not provider or doc.get("provider") == provider)
        ]
        if not matches and provider:
            matches = [doc for doc in (_runtime.get("models") or []) if doc.get("model_name") == model]
        if matches:
            doc = matches[0]
            provider_name = doc.get("provider") or provider or provider_name
            if doc.get("api_base"):
                base_url = str(doc["api_base"]).rstrip("/")
        elif provider:
            provider_name = provider
    cached = (_runtime.get("providers") or {}).get(provider_name) or {}
    if cached and not cached.get("is_active"):
        raise RuntimeError(f"厂家 {provider_name} 已禁用，请在「设置 → 厂家管理」启用或更换 Agent 模型")
    default_url, _ = PROVIDER_CONFIG.get(provider_name, PROVIDER_CONFIG["openai"])
    base_url = cached.get("base_url") or base_url or settings.CUSTOM_OPENAI_BASE_URL or default_url
    from app.services.llm_config_service import resolve_volcengine_base

    base_url = resolve_volcengine_base(provider_name, picked_model, base_url or "")
    api_key = _api_key_for(provider_name)
    if not api_key:
        raise RuntimeError("未配置 LLM API Key，请在「设置 → 厂家管理」中填写，或在 .env 中配置")
    return ChatOpenAI(
        model=picked_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        timeout=120,
        max_retries=2,
    )


def create_agent_llm(
    agent: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.2,
    vision: bool | None = None,
) -> ChatOpenAI:
    binding = (_runtime.get("agent_models") or {}).get(agent) or {}
    use_provider = (provider or binding.get("provider") or "").strip() or None
    use_model = (model or binding.get("model_name") or "").strip() or None
    prefer_vision = vision if vision is not None else agent == "agent1"
    return create_chat_model(use_model, temperature=temperature, vision=prefer_vision, provider=use_provider)


async def persist_agent_models(partial: dict[str, dict] | None) -> dict[str, dict]:
    from app.core.database import get_db

    db = get_db()
    stored = await db.system_config.find_one({"key": "app"}) or {}
    current = ((stored.get("values") or {}).get("agent_models")) or {}
    merged = {
        "agent1": dict(current.get("agent1") or {}) if isinstance(current.get("agent1"), dict) else {},
        "agent2": dict(current.get("agent2") or {}) if isinstance(current.get("agent2"), dict) else {},
        "agent3": dict(current.get("agent3") or {}) if isinstance(current.get("agent3"), dict) else {},
    }
    for key, val in (partial or {}).items():
        if key not in merged or not isinstance(val, dict):
            continue
        merged[key] = {
            "provider": (val.get("provider") or "").strip(),
            "model_name": (val.get("model_name") or "").strip(),
        }
    await db.system_config.update_one(
        {"key": "app"},
        {"$set": {"values.agent_models": merged}},
        upsert=True,
    )
    _runtime["agent_models"] = merged
    return merged


def list_enabled_models() -> list[dict]:
    providers = _runtime.get("providers") or {}
    items = []
    for doc in _runtime.get("models") or []:
        provider_name = doc.get("provider") or ""
        info = providers.get(provider_name) or {}
        if not info.get("is_active") or not info.get("api_key"):
            continue
        items.append(
            {
                "id": f"{provider_name}::{doc.get('model_name')}",
                "provider": provider_name,
                "provider_display_name": info.get("display_name") or provider_name,
                "model_name": doc.get("model_name"),
                "model_display_name": doc.get("model_display_name") or doc.get("model_name"),
                "features": doc.get("features") or [],
                "suitable_roles": doc.get("suitable_roles") or [],
            }
        )
    return items


def extract_json(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


def image_data_url(jpeg_bytes: bytes) -> str:
    b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"
