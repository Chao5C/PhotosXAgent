from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.services.exif_service import extract_exif, image_to_jpeg_bytes
from photosx.graph.state import PhotoAgentState
from photosx.llm.client import create_agent_llm, extract_json, image_data_url, llm_available

logger = logging.getLogger(__name__)

VISION_SYSTEM = """你是 PhotosXAgent 的影像理解 Agent。

## 规则
- 根据图片内容与 EXIF 提示理解影像，输出中文。
- 不要评价人物外貌美丑。
- 看完图后必须调用 submit_vision_result，不要只输出 Markdown。

## 字段说明（全部必填，除 landmark_hint 可空）
- scene_type: group|pet|scenery|food|architecture|other
- people_count: 整数；合照指两人及以上
- objects/tags: 中文短词列表
- caption: **简略描述**，一句话 10–25 字，客观描述画面主体与场景。
  示例：「一只灰鹅站在水边的岩石上」「夕阳下的古城墙与游客」
- long_description: **详细描述**，50–100 个汉字，补充环境、构图、光线、氛围；不要重复 caption 原文。
- landmark_hint: 仅从 EXIF/GPS 可推断的地标名，无法确定则留空（地点由系统逆地理编码，不要编造）

不确定时 scene_type 用 other。
"""

_vision_result: ContextVar[dict[str, Any] | None] = ContextVar("vision_result", default=None)

AI_CAPTION_FALLBACK = "已提取拍摄信息，视觉模型未配置或调用失败。"


@tool
def submit_vision_result(
    scene_type: str = "other",
    people_count: int = 0,
    objects: list[str] | None = None,
    tags: list[str] | None = None,
    caption: str = "",
    long_description: str = "",
    landmark_hint: str = "",
) -> str:
    """提交影像理解结果。看完图后必须调用。"""
    data = {
        "scene_type": scene_type or "other",
        "people_count": int(people_count or 0),
        "objects": objects or [],
        "tags": tags or [],
        "caption": (caption or "").strip(),
        "long_description": (long_description or "").strip(),
        "landmark_hint": (landmark_hint or "").strip(),
        "source": "vision_llm",
    }
    _vision_result.set(data)
    return '{"ok": true}'


VISION_TOOLS = [submit_vision_result]


def _fallback_vision(metadata: dict) -> dict:
    tags = ["未识别"]
    scene = "other"
    if metadata.get("lat") and metadata.get("lng"):
        tags = ["有定位", "待识别"]
        scene = "scenery"
    return {
        "scene_type": scene,
        "people_count": 0,
        "objects": [],
        "tags": tags,
        "caption": AI_CAPTION_FALLBACK,
        "long_description": "",
        "landmark_hint": "",
        "source": "fallback",
    }


def _normalize_vision(raw: dict[str, Any]) -> dict[str, Any]:
    caption = (raw.get("caption") or "").strip()
    long_desc = (raw.get("long_description") or "").strip()
    tags = raw.get("tags") or []
    if not caption and tags:
        caption = "，".join(str(t) for t in tags[:3])
    if not long_desc and caption and caption != AI_CAPTION_FALLBACK:
        long_desc = caption
    return {
        "scene_type": raw.get("scene_type") or "other",
        "people_count": int(raw.get("people_count") or 0),
        "objects": raw.get("objects") or [],
        "tags": tags,
        "caption": caption,
        "long_description": long_desc,
        "landmark_hint": (raw.get("landmark_hint") or "").strip(),
        "source": raw.get("source") or "vision_llm",
    }


def _vision_payload_from_tool_args(args: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(args, dict):
        return None
    payload = {
        "scene_type": args.get("scene_type") or "other",
        "people_count": int(args.get("people_count") or 0),
        "objects": args.get("objects") or [],
        "tags": args.get("tags") or [],
        "caption": (args.get("caption") or "").strip(),
        "long_description": (args.get("long_description") or "").strip(),
        "landmark_hint": (args.get("landmark_hint") or "").strip(),
        "source": "vision_llm",
    }
    if not payload["caption"]:
        return None
    return payload


def _extract_tool_call_result(messages: list) -> dict[str, Any] | None:
    """LangGraph tool execution may not propagate ContextVar; read tool_calls args directly."""
    for msg in reversed(messages or []):
        tool_calls = getattr(msg, "tool_calls", None) or []
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            if name != "submit_vision_result":
                continue
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            payload = _vision_payload_from_tool_args(args)
            if payload:
                return payload
    return None


def _vision_is_usable(raw: dict[str, Any] | None) -> bool:
    if not raw:
        return False
    caption = (raw.get("caption") or "").strip()
    return bool(caption and caption != AI_CAPTION_FALLBACK)


def _is_retryable_llm_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in ("429", "too many requests", "inflightbatchsizeexceeded", "rate limit", "timeout", "timed out")
    )


def _build_exif_hint(metadata: dict) -> str:
    return (
        f"拍摄时间: {metadata.get('taken_at') or '未知'}; "
        f"GPS: {metadata.get('lat')},{metadata.get('lng')}; "
        f"设备: {metadata.get('camera') or '未知'}"
    )


async def _invoke_react_agent(agent, message: HumanMessage) -> dict | None:
    result = await agent.ainvoke({"messages": [message]})
    return _from_messages(result.get("messages") or [])


async def _direct_vision_call(llm, jpeg: bytes, metadata: dict) -> dict | None:
    exif_hint = _build_exif_hint(metadata)
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "请分析这张照片，只返回一个 JSON 对象，不要 Markdown。"
                    "字段: scene_type, people_count, objects, tags, caption, long_description, landmark_hint。"
                    "caption 为 10–25 字中文简略描述；long_description 为 50–100 字中文详细描述。"
                    f" EXIF：{exif_hint}"
                ),
            },
            {"type": "image_url", "image_url": {"url": image_data_url(jpeg)}},
        ]
    )
    resp = await llm.ainvoke([message])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    parsed = extract_json(content)
    if not parsed:
        return None
    parsed["source"] = "vision_llm"
    normalized = _normalize_vision(parsed)
    return normalized if _vision_is_usable(normalized) else None


def _from_messages(messages: list) -> dict | None:
    from_tool = _extract_tool_call_result(messages)
    if _vision_is_usable(from_tool):
        return _normalize_vision(from_tool)

    stored = _vision_result.get() or {}
    if _vision_is_usable(stored):
        return _normalize_vision(stored)

    for msg in reversed(messages or []):
        content = getattr(msg, "content", None) or ""
        if not isinstance(content, str) or "{" not in content:
            continue
        parsed = extract_json(content)
        if not parsed or set(parsed.keys()) <= {"ok"}:
            continue
        if not (parsed.get("caption") or parsed.get("scene_type") or parsed.get("tags")):
            continue
        parsed["source"] = "vision_llm"
        normalized = _normalize_vision(parsed)
        if _vision_is_usable(normalized):
            return normalized
    return None


async def run_vision_agent(state: PhotoAgentState) -> PhotoAgentState:
    file_path = Path(state["file_path"])
    metadata = extract_exif(file_path)
    vision: dict[str, Any] = _fallback_vision(metadata)
    token = _vision_result.set({})
    last_error = ""

    if llm_available():
        try:
            jpeg = image_to_jpeg_bytes(file_path)
            llm = create_agent_llm("agent1", temperature=0.1, vision=True)
            agent = create_react_agent(llm, VISION_TOOLS, prompt=VISION_SYSTEM)
            exif_hint = _build_exif_hint(metadata)
            message = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "请分析这张照片并调用 submit_vision_result。"
                            "caption 必须是一句 10–25 字的简略中文描述；"
                            "long_description 必须是 50–100 字的详细中文描述。"
                            f" EXIF：{exif_hint}"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url(jpeg)}},
                ]
            )

            parsed: dict | None = None
            for attempt in range(3):
                try:
                    parsed = await _invoke_react_agent(agent, message)
                    if parsed:
                        break
                except Exception as exc:
                    last_error = str(exc)
                    if _is_retryable_llm_error(exc) and attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    logger.warning("Vision react agent failed: %s", exc)
                    break

            if parsed:
                vision = parsed
            elif jpeg:
                try:
                    direct = await _direct_vision_call(llm, jpeg, metadata)
                    if direct:
                        vision = direct
                except Exception as exc:
                    last_error = last_error or str(exc)
                    logger.warning("Direct vision fallback failed: %s", exc)

            if not _vision_is_usable(vision) and last_error:
                vision["error"] = last_error[:500]
        except Exception as exc:
            logger.warning("Vision agent failed: %s", exc)
            vision["error"] = str(exc)[:500]
        finally:
            _vision_result.reset(token)

    return {**state, "metadata": metadata, "vision": vision}
