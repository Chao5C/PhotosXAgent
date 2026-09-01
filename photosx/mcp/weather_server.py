"""PhotosXAgent MCP — 天气与地理编码服务。"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from app.services.geo_service import fetch_weather, geocode_place_name
from photosx.agents.analysis_agent import weather_brief

server = MCPServer("photosx-weather")


@server.tool(description="根据经纬度获取 Open-Meteo 天气与简要描述")
async def get_weather(lat: float, lng: float) -> str:
    weather = await fetch_weather(float(lat), float(lng))
    return json.dumps(
        {"weather": weather, "brief": weather_brief(weather), "lat": lat, "lng": lng},
        ensure_ascii=False,
        default=str,
    )


@server.tool(description="将城市/地点名称解析为坐标与 normalized 标签")
async def geocode_place(place: str) -> str:
    geo = await geocode_place_name(place)
    return json.dumps(geo, ensure_ascii=False, default=str)


if __name__ == "__main__":
    server.run(transport="stdio")
