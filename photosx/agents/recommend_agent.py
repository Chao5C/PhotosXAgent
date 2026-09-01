from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.services.geo_service import resolve_photo_place
from photosx.graph.state import PhotoAgentState
from photosx.llm.client import create_agent_llm, extract_json, llm_available

logger = logging.getLogger(__name__)

RECOMMEND_SYSTEM = """你是 PhotosXAgent 的推荐顾问 Agent。

## 规则
- 根据地点变化与天气给出实用建议；不要评价人物外貌。
- 先可调用 summarize_context 确认输入，再必须调用 submit_recommendation 提交结果。

## 输出字段
title 短标题；body 2-4 句中文（天气/穿衣/行程/相册）；priority 为 high 或 normal；type 为 new_place|weather|album。
"""

_rec_result: ContextVar[dict[str, Any] | None] = ContextVar("rec_result", default=None)


def _weather_brief(weather: dict | None) -> str:
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


@tool
def summarize_context(place: str = "", distance_km: float = 0.0, weather_brief: str = "", scene: str = "") -> str:
    """整理推荐上下文，确认地点、距离、天气与场景后再写建议。"""
    far = distance_km >= settings.DISTANCE_THRESHOLD_KM
    return json.dumps(
        {
            "place": place,
            "distance_km": distance_km,
            "far_from_home": far,
            "weather_brief": weather_brief,
            "scene": scene,
            "hint": "若 far_from_home 为 true，priority 倾向 high，type 倾向 new_place。",
        },
        ensure_ascii=False,
    )


@tool
def submit_recommendation(
    title: str,
    body: str,
    priority: str = "normal",
    type: str = "new_place",
) -> str:
    """提交最终推荐结果，必须调用。"""
    data = {
        "title": title,
        "body": body,
        "priority": priority or "normal",
        "type": type or "new_place",
        "source": "recommend_llm",
    }
    _rec_result.set(data)
    return json.dumps({"ok": True, "submitted": data}, ensure_ascii=False)


RECOMMEND_TOOLS = [summarize_context, submit_recommendation]


def _extract_submitted(messages: list) -> dict[str, Any] | None:
    stored = _rec_result.get() or {}
    if stored.get("title") and stored.get("body"):
        return dict(stored)
    for msg in reversed(messages or []):
        content = getattr(msg, "content", None) or ""
        if isinstance(content, str) and "{" in content:
            parsed = extract_json(content)
            if parsed.get("title") and parsed.get("body"):
                return {
                    "title": parsed["title"],
                    "body": parsed["body"],
                    "priority": parsed.get("priority") or "normal",
                    "type": parsed.get("type") or "new_place",
                    "source": "recommend_llm",
                }
    return None


async def run_recommend_agent(state: PhotoAgentState) -> PhotoAgentState:
    geo = state.get("geo") or {}
    vision = state.get("vision") or {}
    metadata = state.get("metadata") or {}
    weather = geo.get("weather")
    distance_km = geo.get("distance_from_home_km")
    place = resolve_photo_place(geo, metadata)
    payload = {
        "place": place,
        "city": geo.get("city"),
        "country": geo.get("country"),
        "distance_km": distance_km,
        "threshold_km": settings.DISTANCE_THRESHOLD_KM,
        "scene": vision.get("scene_type"),
        "tags": vision.get("tags"),
        "caption": vision.get("caption"),
        "weather": _weather_brief(weather),
    }

    recommendation: dict[str, Any] = {
        "title": f"新地点：{payload['place'] or '新地点'}",
        "body": (
            f"检测到照片定位距离常用地点约 {distance_km:.0f} km。"
            f"{_weather_brief(weather)}。建议关注当地天气并整理该地点相册。"
        ),
        "priority": "high" if (distance_km or 0) >= settings.DISTANCE_THRESHOLD_KM else "normal",
        "type": "new_place",
        "source": "heuristic",
    }

    if llm_available():
        token = _rec_result.set({})
        try:
            llm = create_agent_llm("agent2", temperature=0.4, vision=False)
            agent = create_react_agent(llm, RECOMMEND_TOOLS, prompt=RECOMMEND_SYSTEM)
            result = await agent.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                "请根据以下信息给出建议，先可 summarize_context，最后必须 submit_recommendation：\n"
                                f"{json.dumps(payload, ensure_ascii=False, default=str)}"
                            )
                        )
                    ]
                }
            )
            submitted = _extract_submitted(result.get("messages") or [])
            if submitted:
                recommendation = submitted
        except Exception as exc:
            logger.warning("Recommend tool agent failed: %s", exc)
        finally:
            _rec_result.reset(token)

    recommendation["place"] = payload["place"]
    recommendation["distance_km"] = distance_km
    recommendation["weather_brief"] = _weather_brief(weather)
    return {**state, "recommendation": recommendation}
