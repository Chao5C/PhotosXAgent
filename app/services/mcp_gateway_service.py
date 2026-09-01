from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.core.config import ROOT_DIR
from app.utils.serialize import utcnow

logger = logging.getLogger(__name__)

CONFIG_KEY = "mcp_gateway"
CONNECT_TIMEOUT = 25.0


def _python_executable() -> str:
    return sys.executable


def default_gateway_config() -> dict[str, Any]:
    root = str(ROOT_DIR)
    py = _python_executable()
    return {
        "enabled": True,
        "servers": [
            {
                "id": "photosx-search",
                "name": "联网搜索",
                "description": "DuckDuckGo 联网检索，供旅行攻略与 Studio 调研使用",
                "enabled": True,
                "transport": "stdio",
                "command": py,
                "args": ["-m", "photosx.mcp.search_server"],
                "cwd": root,
                "env": {},
                "test_tool": "web_search_tool",
                "test_arguments": {"query": "上海 旅游攻略", "limit": 2},
            },
            {
                "id": "photosx-weather",
                "name": "天气服务",
                "description": "Open-Meteo 天气 + 高德/Nominatim 地理编码",
                "enabled": True,
                "transport": "stdio",
                "command": py,
                "args": ["-m", "photosx.mcp.weather_server"],
                "cwd": root,
                "env": {},
                "test_tool": "geocode_place",
                "test_arguments": {"place": "上海"},
            },
        ],
    }


def _resolve_server(server: dict[str, Any]) -> dict[str, Any]:
    item = dict(server or {})
    cmd = (item.get("command") or "").strip()
    if not cmd or cmd in {"python", "python3", "py"}:
        item["command"] = _python_executable()
    cwd = (item.get("cwd") or "").strip()
    if not cwd:
        item["cwd"] = str(ROOT_DIR)
    item["args"] = [str(a) for a in (item.get("args") or [])]
    item["env"] = {str(k): str(v) for k, v in (item.get("env") or {}).items()}
    return item


class McpGatewayService:
    def __init__(self, db):
        self.db = db

    async def get_config(self) -> dict[str, Any]:
        doc = await self.db.system_config.find_one({"key": CONFIG_KEY}) or {}
        values = doc.get("values") or {}
        if not values.get("servers"):
            return default_gateway_config()
        merged = default_gateway_config()
        merged["enabled"] = values.get("enabled", True)
        by_id = {s.get("id"): s for s in values.get("servers") or [] if s.get("id")}
        servers = []
        for base in merged["servers"]:
            override = by_id.pop(base["id"], {})
            servers.append({**base, **override, "id": base["id"]})
        for extra_id, extra in by_id.items():
            servers.append(_resolve_server(extra))
        merged["servers"] = [_resolve_server(s) for s in servers]
        return merged

    async def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_config()
        current["enabled"] = bool(payload.get("enabled", current.get("enabled", True)))
        incoming = {s.get("id"): s for s in (payload.get("servers") or []) if s.get("id")}
        servers = []
        for base in current.get("servers") or []:
            sid = base.get("id")
            if sid in incoming:
                merged = {**base, **incoming[sid], "id": sid}
                servers.append(_resolve_server(merged))
        for sid, item in incoming.items():
            if sid not in {s.get("id") for s in servers}:
                servers.append(_resolve_server({"id": sid, **item}))
        current["servers"] = servers
        await self.db.system_config.update_one(
            {"key": CONFIG_KEY},
            {"$set": {"values": current, "updated_at": utcnow()}},
            upsert=True,
        )
        return current

    def _find_server(self, config: dict[str, Any], server_id: str) -> dict[str, Any] | None:
        for server in config.get("servers") or []:
            if server.get("id") == server_id:
                return _resolve_server(server)
        return None

    async def is_server_enabled(self, server_id: str) -> bool:
        config = await self.get_config()
        if not config.get("enabled", True):
            return False
        server = self._find_server(config, server_id)
        return bool(server and server.get("enabled", True))

    @asynccontextmanager
    async def _session(self, server: dict[str, Any]):
        params = StdioServerParameters(
            command=server["command"],
            args=server.get("args") or [],
            env=server.get("env") or None,
            cwd=Path(server.get("cwd") or ROOT_DIR),
        )
        async with stdio_client(params) as streams:
            async with ClientSession(streams[0], streams[1], read_timeout_seconds=CONNECT_TIMEOUT) as session:
                await session.initialize()
                yield session

    async def test_server(self, server_id: str) -> dict[str, Any]:
        config = await self.get_config()
        server = self._find_server(config, server_id)
        if not server:
            return {"ok": False, "message": f"未找到 MCP 服务：{server_id}"}
        if not server.get("enabled", True):
            return {"ok": False, "message": "该 MCP 服务已禁用"}
        tool_name = server.get("test_tool") or ""
        arguments = dict(server.get("test_arguments") or {})
        started = utcnow()
        try:
            with anyio.fail_after(CONNECT_TIMEOUT):
                async with self._session(server) as session:
                    tools = await session.list_tools()
                    tool_names = [t.name for t in tools.tools]
                    if tool_name and tool_name not in tool_names:
                        return {
                            "ok": False,
                            "message": f"测试工具 {tool_name} 不存在；可用：{', '.join(tool_names)}",
                            "tools": tool_names,
                        }
                    probe_tool = tool_name or (tool_names[0] if tool_names else "")
                    probe_args = arguments if probe_tool == tool_name else {}
                    result = await session.call_tool(probe_tool, probe_args) if probe_tool else None
                    preview = _tool_result_text(result)
                    elapsed_ms = int((utcnow() - started).total_seconds() * 1000)
                    return {
                        "ok": True,
                        "message": f"连接成功，耗时 {elapsed_ms} ms",
                        "tools": tool_names,
                        "test_tool": probe_tool,
                        "preview": preview[:1200],
                        "elapsed_ms": elapsed_ms,
                    }
        except Exception as exc:
            logger.warning("MCP test failed for %s: %s", server_id, exc)
            return {"ok": False, "message": f"连接失败：{exc}"}

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        config = await self.get_config()
        if not config.get("enabled", True):
            raise RuntimeError("MCP 网关已禁用")
        server = self._find_server(config, server_id)
        if not server or not server.get("enabled", True):
            raise RuntimeError(f"MCP 服务不可用：{server_id}")
        async with self._session(server) as session:
            result = await session.call_tool(tool_name, arguments or {})
            return _tool_result_text(result)


def _tool_result_text(result: Any) -> str:
    if result is None:
        return ""
    content = getattr(result, "content", None) or []
    chunks: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
            continue
        if isinstance(block, dict) and block.get("text"):
            chunks.append(str(block["text"]))
    if chunks:
        return "\n".join(chunks)
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False, default=str)
    if getattr(result, "is_error", False):
        raise RuntimeError(chunks[0] if chunks else "MCP tool error")
    return ""


async def mcp_web_search(db, query: str, limit: int = 6) -> list[dict[str, Any]] | None:
    gateway = McpGatewayService(db)
    if not await gateway.is_server_enabled("photosx-search"):
        return None
    try:
        raw = await gateway.call_tool("photosx-search", "web_search_tool", {"query": query, "limit": limit})
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else None
    except Exception as exc:
        logger.warning("MCP web_search failed, fallback to local: %s", exc)
        return None


async def mcp_geocode_place(db, place: str) -> dict[str, Any] | None:
    gateway = McpGatewayService(db)
    if not await gateway.is_server_enabled("photosx-weather"):
        return None
    try:
        raw = await gateway.call_tool("photosx-weather", "geocode_place", {"place": place})
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("MCP geocode failed, fallback to local: %s", exc)
        return None


async def mcp_fetch_weather(db, lat: float, lng: float) -> dict[str, Any] | None:
    gateway = McpGatewayService(db)
    if not await gateway.is_server_enabled("photosx-weather"):
        return None
    try:
        raw = await gateway.call_tool("photosx-weather", "get_weather", {"lat": lat, "lng": lng})
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("MCP weather failed, fallback to local: %s", exc)
        return None
