from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.geo_service import fetch_weather
from photosx.llm.client import create_agent_llm, extract_json, llm_available
from photosx.studio.research import web_search

logger = logging.getLogger(__name__)

GUIDE_SYSTEM = """你是 PhotosXAgent 的出行攻略顾问。根据用户问题、目的地、天气与联网资料，写出完整可执行的出行建议。

输出格式（严格按此结构，不要 Markdown 代码块）：
【标题】一行短标题
【正文】6-12 句中文，含穿衣、交通、景点/美食/住宿建议；优先引用联网资料中的可核实信息；不要写「检测到连续停留拍照」这类图库触发话术
【亮点】用分号分隔 2-4 条，如：外滩夜景；本帮菜；地铁出行
【追问】1-2 句，顺着用户问题引导下一步，例如是否需要做成海报、查相关照片、细化美食或亲子路线

规则：
- 不要评价人物外貌
- 用户问「想去XX有什么建议」时，直接给客制化攻略，不要描述图库检索过程
- 联网资料不足时，基于常识与天气给出建议，并说明哪些信息建议出发前再核实
"""

GUIDE_JSON_SYSTEM = """你是 PhotosXAgent 的出行攻略顾问。根据用户问题、目的地、天气与联网资料，输出严格 JSON（不要 Markdown）：
{
  "title": "短标题",
  "body": "6-12句完整攻略",
  "highlights": ["亮点1", "亮点2"],
  "follow_up": "顺着用户问题追问下一步",
  "sources_note": "简要说明参考了哪些联网信息"
}
不要写「检测到连续停留拍照」；travel_advice 场景禁止图库触发话术。"""

GUIDE_STREAM_SYSTEM = """你是 PhotosXAgent 的出行攻略顾问。请直接输出给用户看的完整中文建议（不要用 JSON，不要写「检测到连续停留拍照」）。

结构：
1. 第一行：简短标题
2. 空一行
3. 6-12 句正文：穿衣、交通、景点/美食/住宿；结合天气与联网资料
4. 空一行
5. 一行「推荐关注：…；…」
6. 空一行
7. 1-2 句追问用户下一步（如是否做成海报、找照片、细化美食路线）

联网资料不足时，基于常识写建议，并说明哪些需出发前核实。"""


def weather_brief(weather: dict | None) -> str:
    if not weather:
        return "天气数据暂不可用"
    current = weather.get("current_weather") or {}
    daily = weather.get("daily") or {}
    temp = current.get("temperature")
    wind = current.get("windspeed")
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    rain = (daily.get("precipitation_sum") or [None])[0]
    return f"当前气温 {temp}°C，风速 {wind} km/h；今日最高 {tmax}°C / 最低 {tmin}°C，降水 {rain} mm"


def _search_queries(payload: dict[str, Any]) -> list[str]:
    place = (payload.get("place") or payload.get("destination_query") or "目的地").strip()
    question = (payload.get("user_question") or "").strip()
    queries = [
        f"{place} 旅游攻略 景点 交通 2025",
        f"{place} 美食 住宿 穿衣建议",
    ]
    if question and len(question) > 4:
        queries.insert(0, f"{place} {question[:40]}")
    return queries


async def _collect_web_sources(payload: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    use_mcp = False
    try:
        from app.core.database import get_db
        from app.services.mcp_gateway_service import McpGatewayService

        use_mcp = await McpGatewayService(get_db()).is_server_enabled("photosx-search")
    except Exception:
        use_mcp = False

    for query in _search_queries(payload):
        batch: list[dict[str, Any]] = []
        if use_mcp:
            try:
                from app.core.database import get_db
                from app.services.mcp_gateway_service import mcp_web_search

                batch = await mcp_web_search(get_db(), query, limit=3) or []
            except Exception as exc:
                logger.warning("MCP search batch failed: %s", exc)
                batch = []
        if not batch:
            batch = await web_search(query, limit=3)
        for src in batch:
            url = (src.get("url") or "").strip()
            if url and url in seen:
                continue
            if url:
                seen.add(url)
            items.append(src)
            if len(items) >= limit:
                return items
    return items


def _fallback(payload: dict[str, Any]) -> dict[str, Any]:
    place = payload.get("place") or payload.get("destination_query") or "目的地"
    intent = payload.get("intent")
    weather_line = weather_brief(payload.get("weather"))
    if intent == "travel_advice":
        return {
            "title": f"{place}出行参考",
            "body": (
                f"{weather_line}。"
                f"建议出发前核对 {place} 的交通与预约政策，按 2-3 天行程拆分景点与用餐。"
                "热门区域优先地铁/步行，雨天备轻便雨具与防滑鞋。"
            ),
            "topic": "travel",
            "highlights": ["关注天气变化", "提前预约热门景点", "预留机动时间"],
            "follow_up": "你想让我把攻略做成一张海报，还是帮你找图库里相关的照片？",
            "sources_note": "联网资料暂不可用，以上为基于天气与常识的参考建议。",
            "priority": "high",
            "source": "heuristic",
        }
    return {
        "title": f"新地点攻略：{place}",
        "body": (
            f"检测到你在 {place} 连续停留拍照。{weather_line}。"
            "建议先确认交通与住宿，并整理该地点相册。"
        ),
        "topic": "travel",
        "highlights": ["关注天气", "整理相册"],
        "follow_up": "需要我把这份建议整理成海报吗？",
        "sources_note": "",
        "priority": "high",
        "source": "heuristic",
    }


def _parse_structured_text(text: str) -> dict[str, Any] | None:
    blob = (text or "").strip()
    if not blob:
        return None

    def section(name: str) -> str:
        m = re.search(rf"【{name}】\s*(.*?)(?=【|$)", blob, flags=re.S)
        return (m.group(1).strip() if m else "")

    title = section("标题")
    body = section("正文")
    highlights_raw = section("亮点")
    follow_up = section("追问")
    if not title or not body:
        parsed = extract_json(blob)
        if parsed.get("title") and parsed.get("body"):
            return {
                "title": parsed["title"],
                "body": parsed["body"],
                "highlights": parsed.get("highlights") or [],
                "follow_up": parsed.get("follow_up") or "",
                "sources_note": parsed.get("sources_note") or "",
                "topic": parsed.get("topic") or "travel",
                "priority": parsed.get("priority") or "high",
                "source": "analysis_llm",
            }
        return None
    highlights = [h.strip() for h in re.split(r"[;；\n]", highlights_raw) if h.strip()]
    return {
        "title": title,
        "body": body,
        "highlights": highlights,
        "follow_up": follow_up,
        "sources_note": "",
        "topic": "travel",
        "priority": "high",
        "source": "analysis_llm",
    }


def _format_reply(guide: dict[str, Any], *, related_photo_count: int = 0, place: str = "") -> str:
    lines = [guide.get("title") or "", guide.get("body") or ""]
    highlights = [h for h in (guide.get("highlights") or []) if h]
    if highlights:
        lines.append("推荐关注：" + "；".join(highlights))
    sources_note = (guide.get("sources_note") or "").strip()
    if sources_note:
        lines.append(sources_note)
    follow_up = (guide.get("follow_up") or "").strip()
    if follow_up:
        lines.append(follow_up)
    if "海报" not in "\n".join(lines):
        lines.append("需要我把以上攻略做成一张海报并保存到海报图库吗？回复「生成海报」即可，不会自动生成。")
    if related_photo_count and place:
        lines.append(
            f"你的图库里有 {related_photo_count} 张与{place}相关的照片；若要查看可以说「找{place}的照片」。"
        )
    return "\n\n".join(line for line in lines if line)


async def _generate_with_llm(payload: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _fallback(payload)
    if not llm_available():
        return fallback
    llm = create_agent_llm("agent2", temperature=0.45, vision=False)
    if payload.get("lat") is not None and payload.get("lng") is not None and not payload.get("weather"):
        payload["weather"] = await fetch_weather(float(payload["lat"]), float(payload["lng"]))
        payload["weather_brief"] = weather_brief(payload.get("weather"))
    context = {
        **payload,
        "weather_brief": payload.get("weather_brief") or weather_brief(payload.get("weather")),
        "web_sources": sources,
    }
    try:
        resp = await llm.ainvoke(
            [
                SystemMessage(content=GUIDE_JSON_SYSTEM),
                HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)[:12000]),
            ]
        )
        parsed = extract_json(getattr(resp, "content", "") or "")
        if parsed.get("title") and parsed.get("body"):
            parsed.setdefault("topic", "travel")
            parsed.setdefault("priority", "high")
            parsed.setdefault("follow_up", "")
            parsed.setdefault("sources_note", f"已参考 {len(sources)} 条联网资料。" if sources else "")
            parsed["source"] = "analysis_llm"
            return parsed
    except Exception as exc:
        logger.warning("Guide JSON LLM failed: %s", exc)

    try:
        resp = await llm.ainvoke(
            [
                SystemMessage(content=GUIDE_SYSTEM),
                HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)[:12000]),
            ]
        )
        parsed = _parse_structured_text(getattr(resp, "content", "") or "")
        if parsed:
            if sources and not parsed.get("sources_note"):
                parsed["sources_note"] = f"已参考 {len(sources)} 条联网资料。"
            return parsed
    except Exception as exc:
        logger.warning("Guide text LLM failed: %s", exc)
    return fallback


async def generate_guide(payload: dict[str, Any]) -> dict[str, Any]:
    sources = await _collect_web_sources(payload)
    payload = {**payload, "web_sources": sources}
    return await _generate_with_llm(payload, sources)


async def stream_travel_guide(payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE-friendly events while building a travel guide."""
    yield {"type": "status", "content": "正在联网检索最新出行信息…"}
    sources = await _collect_web_sources(payload)
    yield {
        "type": "status",
        "content": f"已找到 {len(sources)} 条参考信息，正在撰写完整建议…",
    }
    payload = {**payload, "web_sources": sources}
    if payload.get("lat") is not None and payload.get("lng") is not None and not payload.get("weather"):
        payload["weather"] = await fetch_weather(float(payload["lat"]), float(payload["lng"]))
    payload["weather_brief"] = payload.get("weather_brief") or weather_brief(payload.get("weather"))

    if not llm_available():
        guide = _fallback(payload)
        reply = _format_reply(guide)
        yield {"type": "token", "content": reply}
        yield {"type": "done", "guide": guide, "reply": reply}
        return

    llm = create_agent_llm("agent2", temperature=0.45, vision=False)
    buffer = ""
    try:
        async for chunk in llm.astream(
            [
                SystemMessage(content=GUIDE_STREAM_SYSTEM),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)[:12000]),
            ]
        ):
            token = chunk.content if isinstance(chunk.content, str) else ""
            if not token:
                continue
            buffer += token
            yield {"type": "token", "content": token}
    except Exception as exc:
        logger.warning("stream_travel_guide failed: %s", exc)
        guide = _fallback(payload)
        reply = _format_reply(guide)
        if not buffer.strip():
            yield {"type": "token", "content": reply}
        yield {"type": "done", "guide": guide, "reply": reply if not buffer.strip() else _format_reply(guide)}
        return

    guide = _parse_structured_text(buffer)
    if not guide:
        lines = [line.strip() for line in buffer.split("\n") if line.strip()]
        if len(lines) >= 2:
            title = lines[0]
            body_lines = []
            highlights = []
            follow_up = ""
            for line in lines[1:]:
                if line.startswith("推荐关注："):
                    highlights = [p.strip() for p in line.replace("推荐关注：", "").split("；") if p.strip()]
                elif "？" in line or "?" in line:
                    follow_up = line
                else:
                    body_lines.append(line)
            guide = {
                "title": title,
                "body": "\n".join(body_lines).strip(),
                "highlights": highlights,
                "follow_up": follow_up,
                "topic": "travel",
                "priority": "high",
                "source": "analysis_llm",
            }
    if not guide:
        guide = _fallback(payload)
    if sources and not guide.get("sources_note"):
        guide["sources_note"] = f"已参考 {len(sources)} 条联网资料。"
    reply = _format_reply(guide)
    yield {"type": "done", "guide": guide, "reply": reply}
