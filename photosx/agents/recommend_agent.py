from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from photosx.graph.state import PhotoAgentState
from photosx.llm.client import create_agent_llm, extract_json, llm_available

logger = logging.getLogger(__name__)

RECOMMEND_SYSTEM = """你是 PhotosXAgent 的推荐顾问 Agent。根据用户照片地点变化与天气，给出实用建议。
只输出 JSON：
{
  "title": "短标题",
  "body": "2-4句中文建议，包含天气、穿衣、行程或相册建议",
  "priority": "high|normal",
  "type": "new_place|weather|album"
}
"""


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


async def run_recommend_agent(state: PhotoAgentState) -> PhotoAgentState:
    geo = state.get("geo") or {}
    vision = state.get("vision") or {}
    weather = geo.get("weather")
    distance_km = geo.get("distance_from_home_km")
    payload = {
        "place": geo.get("place_name") or geo.get("city"),
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
        "title": f"新地点：{payload['place'] or '未知地点'}",
        "body": f"检测到照片定位距离常用地点约 {distance_km:.0f} km。{_weather_brief(weather)}。建议关注当地天气并整理该地点相册。",
        "priority": "high" if (distance_km or 0) >= settings.DISTANCE_THRESHOLD_KM else "normal",
        "type": "new_place",
        "source": "heuristic",
    }

    if llm_available():
        try:
            llm = create_agent_llm("agent2", temperature=0.4, vision=False)
            response = await llm.ainvoke(
                [
                    SystemMessage(content=RECOMMEND_SYSTEM),
                    HumanMessage(content=f"请根据以下信息给出建议：{payload}"),
                ]
            )
            parsed = extract_json(getattr(response, "content", "") or str(response))
            if parsed.get("title") and parsed.get("body"):
                recommendation = {
                    "title": parsed["title"],
                    "body": parsed["body"],
                    "priority": parsed.get("priority") or recommendation["priority"],
                    "type": parsed.get("type") or "new_place",
                    "source": "recommend_llm",
                }
        except Exception as exc:
            logger.warning("Recommend agent LLM failed: %s", exc)

    recommendation["place"] = payload["place"]
    recommendation["distance_km"] = distance_km
    recommendation["weather_brief"] = _weather_brief(weather)
    return {**state, "recommendation": recommendation}
