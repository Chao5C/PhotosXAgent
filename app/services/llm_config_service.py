from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.utils.serialize import serialize, utcnow

ENV_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "volcengine": "VOLCENGINE_API_KEY",
    "volcengine_coding": "VOLCENGINE_CODING_API_KEY",
    "custom_openai": "CUSTOM_OPENAI_API_KEY",
}

VOLCENGINE_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLCENGINE_CODING_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
CODING_MODELS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "doubao-seed-2.0-code",
    "doubao-seed-code",
    "kimi-k2.7-code",
}


def resolve_volcengine_base(provider: str, model: str, current_base: str = "") -> str:
    name = (model or "").strip().lower()
    provider = (provider or "").lower()
    current = (current_base or "").rstrip("/")
    if provider == "volcengine_coding" or name in CODING_MODELS:
        return VOLCENGINE_CODING_BASE
    if current:
        return current
    if provider.startswith("volcengine"):
        return VOLCENGINE_BASE
    return current

DEFAULT_PROVIDERS = [
    {
        "name": "volcengine",
        "display_name": "火山方舟",
        "description": "字节跳动火山方舟，支持 Doubao / DeepSeek 等模型。",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "test_model": "doubao-seed-1-6-flash",
        "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"],
        "is_active": True,
        "website": "https://www.volcengine.com/product/ark",
    },
    {
        "name": "volcengine_coding",
        "display_name": "火山方舟编程",
        "description": "火山方舟编程版接口。deepseek-v4-flash / Pro 必须走 /api/coding/v3，普通 api/v3 会返回模型不存在。",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "test_model": "deepseek-v4-flash",
        "supported_features": ["chat", "completion", "function_calling", "streaming"],
        "is_active": True,
        "website": "https://www.volcengine.com/docs/82379/1925114",
    },
    {
        "name": "deepseek",
        "display_name": "DeepSeek",
        "description": "DeepSeek 对话与推理模型。",
        "default_base_url": "https://api.deepseek.com",
        "test_model": "deepseek-chat",
        "supported_features": ["chat", "completion", "function_calling", "streaming"],
        "is_active": True,
        "website": "https://platform.deepseek.com",
    },
    {
        "name": "ollama",
        "display_name": "Ollama（本地模型）",
        "description": "本地部署开源模型，无需云端密钥。",
        "default_base_url": "http://localhost:11434/v1",
        "test_model": "llama3.1",
        "supported_features": ["chat", "completion", "embedding", "streaming"],
        "is_active": True,
        "website": "https://ollama.com",
    },
    {
        "name": "dashscope",
        "display_name": "阿里云百炼",
        "description": "通义千问系列，含 qwen-vl 视觉模型，适合 Agent1 识图。",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "test_model": "qwen-plus",
        "supported_features": ["chat", "completion", "embedding", "vision", "function_calling", "streaming"],
        "is_active": False,
        "website": "https://bailian.console.aliyun.com",
    },
    {
        "name": "openai",
        "display_name": "OpenAI",
        "description": "GPT-4o 等通用与视觉模型。",
        "default_base_url": "https://api.openai.com/v1",
        "test_model": "gpt-4o-mini",
        "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"],
        "is_active": False,
        "website": "https://platform.openai.com",
    },
]

DEFAULT_CATALOGS = [
    {
        "provider": "dashscope",
        "provider_name": "通义千问",
        "models": [
            {"name": "qwen-vl-max", "display_name": "Qwen-VL-Max 视觉旗舰"},
            {"name": "qwen-vl-plus", "display_name": "Qwen-VL-Plus 视觉"},
            {"name": "qwen-plus", "display_name": "Qwen-Plus"},
            {"name": "qwen-turbo", "display_name": "Qwen-Turbo"},
        ],
    },
    {
        "provider": "openai",
        "provider_name": "OpenAI",
        "models": [
            {"name": "gpt-4o", "display_name": "GPT-4o"},
            {"name": "gpt-4o-mini", "display_name": "GPT-4o Mini"},
        ],
    },
    {
        "provider": "deepseek",
        "provider_name": "DeepSeek",
        "models": [
            {"name": "deepseek-chat", "display_name": "DeepSeek Chat"},
            {"name": "deepseek-reasoner", "display_name": "DeepSeek Reasoner"},
        ],
    },
    {
        "provider": "volcengine",
        "provider_name": "火山方舟",
        "models": [
            {"name": "doubao-seed-1-6-flash", "display_name": "Doubao Seed Flash"},
            {"name": "doubao-seed-1-6", "display_name": "Doubao Seed"},
            {"name": "deepseek-v4", "display_name": "DeepSeek-V4"},
        ],
    },
    {
        "provider": "volcengine_coding",
        "provider_name": "火山方舟编程",
        "models": [
            {"name": "deepseek-v4-flash", "display_name": "DeepSeek-V4-Flash"},
            {"name": "deepseek-v4-pro", "display_name": "DeepSeek-V4-Pro"},
            {"name": "doubao-seed-2.0-code", "display_name": "Doubao-Seed-2.0-Code"},
        ],
    },
    {
        "provider": "ollama",
        "provider_name": "Ollama（本地模型）",
        "models": [
            {"name": "llama3.1", "display_name": "Llama 3.1"},
            {"name": "qwen2.5vl", "display_name": "Qwen2.5-VL 本地视觉"},
            {"name": "llava", "display_name": "LLaVA"},
        ],
    },
]

DEFAULT_MODELS = [
    {
        "provider": "dashscope",
        "model_name": "qwen-vl-max",
        "model_display_name": "Qwen-VL-Max 视觉旗舰",
        "max_tokens": 8000,
        "temperature": 0.2,
        "timeout": 180,
        "enabled": True,
        "capability_level": 5,
        "suitable_roles": ["vision"],
        "features": ["vision"],
        "recommended_depths": ["标准", "深度"],
    },
    {
        "provider": "dashscope",
        "model_name": "qwen-plus",
        "model_display_name": "Qwen-Plus",
        "max_tokens": 8000,
        "temperature": 0.3,
        "timeout": 120,
        "enabled": True,
        "capability_level": 4,
        "suitable_roles": ["assistant"],
        "features": ["chat"],
        "recommended_depths": ["快速", "标准"],
    },
    {
        "provider": "volcengine_coding",
        "model_name": "deepseek-v4-flash",
        "model_display_name": "DeepSeek-V4-Flash",
        "api_base": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "max_tokens": 8000,
        "temperature": 0.3,
        "timeout": 180,
        "enabled": True,
        "capability_level": 4,
        "suitable_roles": ["assistant"],
        "features": ["chat"],
        "recommended_depths": ["快速", "标准"],
    },
    {
        "provider": "ollama",
        "model_name": "llama3.1",
        "model_display_name": "Llama 3.1（本地 Ollama）",
        "api_base": "http://localhost:11434/v1",
        "max_tokens": 8000,
        "temperature": 0.3,
        "timeout": 180,
        "enabled": True,
        "capability_level": 3,
        "suitable_roles": ["assistant"],
        "features": ["chat"],
        "recommended_depths": ["快速", "标准"],
    },
]


def env_api_key(provider: str) -> str:
    env_name = ENV_KEY_MAP.get(provider)
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
    key = ""
    if env_name:
        key = (mapped.get(env_name) or os.environ.get(env_name) or "").strip()
    if not key and provider.startswith("volcengine"):
        key = (
            settings.VOLCENGINE_CODING_API_KEY
            or settings.VOLCENGINE_API_KEY
            or os.environ.get("VOLCENGINE_CODING_API_KEY", "")
            or os.environ.get("VOLCENGINE_API_KEY", "")
        ).strip()
    return key


class LLMConfigService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.providers = db.llm_providers
        self.catalogs = db.model_catalogs
        self.models = db.llm_models

    async def ensure_defaults(self) -> None:
        await self.providers.create_index("name", unique=True)
        await self.catalogs.create_index("provider", unique=True)
        await self.models.create_index([("provider", 1), ("model_name", 1)], unique=True)
        now = utcnow()
        for item in DEFAULT_PROVIDERS:
            await self.providers.update_one(
                {"name": item["name"]},
                {"$setOnInsert": {**item, "created_at": now, "updated_at": now}},
                upsert=True,
            )
        for item in DEFAULT_CATALOGS:
            await self.catalogs.update_one(
                {"provider": item["provider"]},
                {"$setOnInsert": {**item, "created_at": now, "updated_at": now}},
                upsert=True,
            )
        for item in DEFAULT_MODELS:
            await self.models.update_one(
                {"provider": item["provider"], "model_name": item["model_name"]},
                {"$setOnInsert": {**item, "created_at": now, "updated_at": now}},
                upsert=True,
            )
        ollama_model = (settings.OLLAMA_MODEL or "llama3.1").strip()
        ollama_base = (settings.OLLAMA_BASE_URL or "http://localhost:11434/v1").rstrip("/")
        await self.providers.update_one(
            {"name": "ollama"},
            {
                "$set": {
                    "default_base_url": ollama_base,
                    "test_model": ollama_model,
                    "updated_at": now,
                }
            },
        )
        await self.models.update_one(
            {"provider": "ollama", "model_name": ollama_model},
            {
                "$setOnInsert": {
                    "provider": "ollama",
                    "model_name": ollama_model,
                    "model_display_name": f"{ollama_model}（本地 Ollama）",
                    "api_base": ollama_base,
                    "max_tokens": 8000,
                    "temperature": 0.3,
                    "timeout": 180,
                    "enabled": True,
                    "capability_level": 3,
                    "suitable_roles": ["assistant"],
                    "features": ["chat"],
                    "recommended_depths": ["快速", "标准"],
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    def _public_provider(self, doc: dict) -> dict:
        item = serialize(doc) or {}
        db_key = (doc.get("api_key") or "").strip()
        env_key = env_api_key(doc.get("name", ""))
        has_key = bool(db_key or env_key) or doc.get("name") == "ollama"
        item["api_key"] = db_key
        item["extra_config"] = {
            "has_api_key": has_key,
            "source": "database" if db_key else ("environment" if env_key else None),
        }
        return item

    async def list_providers(self) -> list[dict]:
        cursor = self.providers.find().sort("created_at", 1)
        return [self._public_provider(doc) async for doc in cursor]

    async def get_provider(self, name: str) -> Optional[dict]:
        return await self.providers.find_one({"name": name})

    async def upsert_provider(self, payload: dict, is_new: bool = False) -> dict:
        name = payload["name"]
        now = utcnow()
        existing = await self.providers.find_one({"name": name})
        if is_new and existing:
            raise ValueError("厂家已存在")
        data = {k: v for k, v in payload.items() if k not in ("id", "_id", "created_at") and v is not None}
        incoming_key = str(data.get("api_key") or "").strip()
        if (not incoming_key) or ("****" in incoming_key):
            data.pop("api_key", None)
        data["updated_at"] = now
        await self.providers.update_one(
            {"name": name},
            {"$set": data, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        doc = await self.providers.find_one({"name": name})
        return self._public_provider(doc or {})

    async def toggle_provider(self, name: str, is_active: bool) -> dict:
        await self.providers.update_one({"name": name}, {"$set": {"is_active": is_active, "updated_at": utcnow()}})
        doc = await self.providers.find_one({"name": name})
        if not doc:
            raise ValueError("厂家不存在")
        return self._public_provider(doc)

    async def delete_provider(self, name: str) -> None:
        await self.providers.delete_one({"name": name})
        await self.catalogs.delete_one({"provider": name})
        await self.models.delete_many({"provider": name})

    async def resolve_api(self, provider_name: str, model: str = "") -> tuple[str, str]:
        provider = await self.providers.find_one({"name": provider_name}) or {}
        api_key = (provider.get("api_key") or "").strip() or env_api_key(provider_name)
        if not api_key and provider_name.startswith("volcengine"):
            sibling_name = "volcengine" if provider_name == "volcengine_coding" else "volcengine_coding"
            sibling = await self.providers.find_one({"name": sibling_name}) or {}
            api_key = (sibling.get("api_key") or "").strip() or env_api_key(sibling_name)
        if provider_name == "ollama":
            api_key = api_key or "ollama"
            base_url = (settings.OLLAMA_BASE_URL or provider.get("default_base_url") or "http://localhost:11434/v1").rstrip("/")
            return api_key, base_url
        base_url = resolve_volcengine_base(provider_name, model, provider.get("default_base_url") or "")
        return api_key, base_url

    async def test_provider(self, name: str) -> dict:
        provider = await self.providers.find_one({"name": name})
        if not provider:
            raise ValueError("厂家不存在")
        model = provider.get("test_model") or "gpt-4o-mini"
        api_key, base_url = await self.resolve_api(name, model)
        if not api_key:
            raise ValueError("未配置 API Key")
        if not base_url:
            raise ValueError("未配置 API 地址")
        return await self._ping_chat(base_url, api_key, model, name)

    async def list_catalogs(self) -> list[dict]:
        cursor = self.catalogs.find().sort("updated_at", -1)
        return [serialize(doc) async for doc in cursor]

    async def upsert_catalog(self, payload: dict) -> dict:
        now = utcnow()
        provider = payload["provider"]
        data = {
            "provider": provider,
            "provider_name": payload.get("provider_name") or provider,
            "models": payload.get("models") or [],
            "updated_at": now,
        }
        await self.catalogs.update_one(
            {"provider": provider},
            {"$set": data, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return serialize(await self.catalogs.find_one({"provider": provider})) or {}

    async def delete_catalog(self, provider: str) -> None:
        await self.catalogs.delete_one({"provider": provider})

    async def list_models(self) -> list[dict]:
        cursor = self.models.find().sort([("provider", 1), ("created_at", 1)])
        return [serialize(doc) async for doc in cursor]

    async def upsert_model(self, payload: dict) -> dict:
        now = utcnow()
        query = {"provider": payload["provider"], "model_name": payload["model_name"]}
        data = {k: v for k, v in payload.items() if k not in ("id", "_id")}
        data["updated_at"] = now
        await self.models.update_one(query, {"$set": data, "$setOnInsert": {"created_at": now}}, upsert=True)
        return serialize(await self.models.find_one(query)) or {}

    async def toggle_model(self, provider: str, model_name: str, enabled: bool) -> dict:
        result = await self.models.update_one(
            {"provider": provider, "model_name": model_name},
            {"$set": {"enabled": enabled, "updated_at": utcnow()}},
        )
        if result.matched_count == 0:
            raise ValueError("模型不存在")
        return serialize(await self.models.find_one({"provider": provider, "model_name": model_name})) or {}

    async def delete_model(self, provider: str, model_name: str) -> None:
        await self.models.delete_one({"provider": provider, "model_name": model_name})

    async def test_model(self, provider: str, model_name: str) -> dict:
        api_key, base_url = await self.resolve_api(provider, model_name)
        model = await self.models.find_one({"provider": provider, "model_name": model_name}) or {}
        if model.get("api_base"):
            base_url = resolve_volcengine_base(provider, model_name, str(model["api_base"]))
        if not api_key:
            raise ValueError("未配置 API Key")
        return await self._ping_chat(base_url, api_key, model_name, provider)

    async def _ping_chat(self, base_url: str, api_key: str, model: str, provider: str = "") -> dict:
        bases = []
        primary = resolve_volcengine_base(provider, model, base_url).rstrip("/")
        bases.append(primary)
        if "volces.com" in primary:
            alt = VOLCENGINE_BASE if "/coding/" in primary else VOLCENGINE_CODING_BASE
            if alt not in bases:
                bases.append(alt)

        last_error = "测试失败"
        for candidate in bases:
            url = f"{candidate}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 64,
            }
            if "volces.com" in candidate:
                payload["thinking"] = {"type": "disabled"}
            async with httpx.AsyncClient(timeout=40.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code < 400:
                data = resp.json()
                message = ((data.get("choices") or [{}])[0].get("message") or {})
                content = message.get("content") or message.get("reasoning_content") or ""
                return {"ok": True, "model": model, "base_url": candidate, "reply": str(content)[:200]}
            last_error = f"测试失败 ({resp.status_code}): {resp.text[:300]}"
            if "InvalidEndpointOrModel" not in resp.text and resp.status_code != 404:
                break
        raise ValueError(last_error)
