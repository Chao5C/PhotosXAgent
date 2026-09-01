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


def ollama_native_base(openai_compat_url: str = "") -> str:
    url = (openai_compat_url or "http://localhost:11434/v1").rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/") or "http://localhost:11434"


def ollama_is_vision(model_name: str) -> bool:
    name = (model_name or "").lower()
    return any(hint in name for hint in ("vl", "llava", "vision", "minicpm-v", "bakllava", "moondream"))


def ensure_openai_v1_base(base_url: str) -> str:
    """Normalize OpenAI-compatible base URLs for /chat/completions calls."""
    url = (base_url or "").rstrip("/")
    if not url:
        return url
    if url.endswith("/v1"):
        return url
    # DeepSeek / DashScope compatible endpoints need /v1; Volcengine already includes path.
    if "volces.com" in url or "openai.com" in url:
        return url
    return f"{url}/v1"


def resolve_volcengine_base(provider: str, model: str, current_base: str = "") -> str:
    """Pick API base URL. Only Volcengine providers may use Volcengine endpoints."""
    name = (model or "").strip().lower()
    provider = (provider or "").lower()
    current = (current_base or "").rstrip("/")
    if not provider.startswith("volcengine"):
        return ensure_openai_v1_base(current)
    if provider == "volcengine_coding" or name in CODING_MODELS:
        return current or VOLCENGINE_CODING_BASE
    return current or VOLCENGINE_BASE

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
                    "updated_at": now,
                },
                "$setOnInsert": {"test_model": ollama_model},
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
        now = utcnow()
        await self.providers.update_one({"name": name}, {"$set": {"is_active": is_active, "updated_at": now}})
        # 火山方舟与火山方舟编程共用密钥/入口，禁用主入口时一并禁用编程版，避免仍走 Volcengine。
        if name == "volcengine" and not is_active:
            await self.providers.update_one(
                {"name": "volcengine_coding"},
                {"$set": {"is_active": False, "updated_at": now}},
            )
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
            if sibling.get("is_active"):
                api_key = (sibling.get("api_key") or "").strip() or env_api_key(sibling_name)
        if provider_name == "ollama":
            api_key = api_key or "ollama"
            base_url = (settings.OLLAMA_BASE_URL or provider.get("default_base_url") or "http://localhost:11434/v1").rstrip("/")
            return api_key, base_url
        model_doc = {}
        if model:
            model_doc = await self.models.find_one({"provider": provider_name, "model_name": model}) or {}
        raw_base = (model_doc.get("api_base") or provider.get("default_base_url") or "").strip()
        base_url = resolve_volcengine_base(provider_name, model, raw_base)
        return api_key, base_url

    async def test_provider(self, name: str) -> dict:
        provider = await self.providers.find_one({"name": name})
        if not provider:
            raise ValueError("厂家不存在")
        if not provider.get("is_active", True):
            raise ValueError("该厂家已禁用，请先启用后再测试")
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
        provider_doc = await self.providers.find_one({"name": provider}) or {}
        if not provider_doc:
            raise ValueError("厂家不存在")
        if not provider_doc.get("is_active", True):
            raise ValueError("该厂家已禁用，请先启用后再测试")
        api_key, base_url = await self.resolve_api(provider, model_name)
        if not api_key:
            raise ValueError("未配置 API Key")
        return await self._ping_chat(base_url, api_key, model_name, provider)

    async def _ollama_host(self) -> str:
        provider = await self.providers.find_one({"name": "ollama"}) or {}
        return ollama_native_base(
            settings.OLLAMA_BASE_URL or provider.get("default_base_url") or "http://localhost:11434/v1"
        )

    async def list_ollama_local(self) -> list[dict]:
        host = await self._ollama_host()
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(f"{host}/api/tags")
        except httpx.ConnectError as exc:
            raise ValueError(
                f"无法连接 Ollama（{host}）。请先在本机启动 Ollama，并确认 OLLAMA_BASE_URL 指向 http://localhost:11434/v1。"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"读取 Ollama 模型列表失败: {exc}") from exc
        if resp.status_code >= 400:
            raise ValueError(f"读取 Ollama 模型列表失败 ({resp.status_code}): {resp.text[:200]}")
        items = []
        for raw in (resp.json() or {}).get("models") or []:
            name = (raw.get("name") or raw.get("model") or "").strip()
            if not name:
                continue
            caps = raw.get("capabilities") or []
            embedding_only = bool(caps) and "completion" not in caps and "embedding" in caps
            items.append(
                {
                    "name": name,
                    "display_name": name,
                    "size": raw.get("size"),
                    "modified_at": raw.get("modified_at"),
                    "vision": ollama_is_vision(name),
                    "embedding_only": embedding_only,
                }
            )
        return items

    async def sync_ollama_models(self) -> dict:
        local = await self.list_ollama_local()
        chat_models = [item for item in local if not item.get("embedding_only")]
        if not chat_models:
            raise ValueError("Ollama 已连接，但没有可用于对话的模型。请先执行例如：ollama pull qwen3:4b")
        host = await self._ollama_host()
        openai_base = f"{host}/v1"
        now = utcnow()
        await self.upsert_catalog(
            {
                "provider": "ollama",
                "provider_name": "Ollama（本地模型）",
                "models": [{"name": item["name"], "display_name": item["display_name"]} for item in chat_models],
            }
        )
        created = 0
        for item in chat_models:
            vision = bool(item.get("vision"))
            existing = await self.models.find_one({"provider": "ollama", "model_name": item["name"]})
            if not existing:
                created += 1
            await self.upsert_model(
                {
                    "provider": "ollama",
                    "model_name": item["name"],
                    "model_display_name": f"{item['name']}（本地 Ollama）",
                    "api_base": openai_base,
                    "max_tokens": 8000,
                    "temperature": 0.3,
                    "timeout": 180,
                    "enabled": True,
                    "capability_level": 3,
                    "suitable_roles": ["vision"] if vision else ["assistant"],
                    "features": ["vision"] if vision else ["chat"],
                    "recommended_depths": ["快速", "标准"],
                }
            )
        names = {item["name"] for item in chat_models}
        provider = await self.providers.find_one({"name": "ollama"}) or {}
        test_model = (provider.get("test_model") or "").strip()
        update = {"default_base_url": openai_base, "is_active": True, "updated_at": now}
        if test_model not in names:
            update["test_model"] = chat_models[0]["name"]
        await self.providers.update_one({"name": "ollama"}, {"$set": update})
        return {"count": len(chat_models), "created": created, "models": [item["name"] for item in chat_models]}

    async def _ping_chat(self, base_url: str, api_key: str, model: str, provider: str = "") -> dict:
        bases = []
        primary = resolve_volcengine_base(provider, model, base_url).rstrip("/")
        bases.append(primary)
        if (provider or "").startswith("volcengine") and "volces.com" in primary:
            alt = VOLCENGINE_BASE if "/coding/" in primary else VOLCENGINE_CODING_BASE
            if alt not in bases:
                bases.append(alt)

        is_local = provider == "ollama" or any(host in (base_url or "") for host in ("localhost", "127.0.0.1"))
        timeout = 120.0 if is_local else 40.0
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
            try:
                async with httpx.AsyncClient(timeout=timeout, trust_env=not is_local) as client:
                    resp = await client.post(url, headers=headers, json=payload)
            except httpx.ConnectError as exc:
                hint = "请确认本机已启动 Ollama（ollama serve），并用 ollama list 查看已拉取模型。" if is_local else ""
                raise ValueError(f"无法连接 {candidate}。{hint}".strip()) from exc
            except httpx.TimeoutException as exc:
                raise ValueError(
                    f"请求超时（{int(timeout)}s）。本地模型首次加载较慢，可稍后再试或换更小的模型。"
                ) from exc
            if resp.status_code < 400:
                data = resp.json()
                message = ((data.get("choices") or [{}])[0].get("message") or {})
                content = message.get("content") or message.get("reasoning_content") or ""
                return {"ok": True, "model": model, "base_url": candidate, "reply": str(content)[:200]}
            last_error = f"测试失败 ({resp.status_code}): {resp.text[:300]}"
            if is_local and resp.status_code in (400, 404):
                try:
                    installed = ", ".join(item["name"] for item in await self.list_ollama_local()) or "（无）"
                    last_error += f"。本机已安装: {installed}。模型名必须与 ollama list 完全一致（含 tag，例如 qwen3:4b）。"
                except ValueError:
                    pass
            if "InvalidEndpointOrModel" not in resp.text and resp.status_code != 404:
                break
        raise ValueError(last_error)
