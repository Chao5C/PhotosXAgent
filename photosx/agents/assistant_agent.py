from __future__ import annotations

import json
import logging
from typing import Any, List

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from app.core.database import get_db
from app.utils.serialize import serialize
from photosx.graph.state import ChatAgentState
from photosx.llm.client import create_agent_llm, llm_available

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM = """你是 PhotosXAgent 的助手 Agent，用简洁中文帮助用户管理照片。
可以调用工具查询图库、相册、行程和推荐。不要编造不存在的照片。
若用户要做自媒体选题，可以基于现有相册和标签给出方向，但说明工作台功能仍在建设中。
"""


def _tools_for_user(user_id: str):
    db = get_db()

    @tool
    async def search_photos(query: str = "", tag: str = "", limit: int = 8) -> str:
        """按关键词、标签搜索用户照片。"""
        filters: dict[str, Any] = {"user_id": user_id, "status": {"$ne": "deleted"}}
        clauses = []
        if query:
            clauses.append({"$or": [
                {"filename": {"$regex": query, "$options": "i"}},
                {"vision.caption": {"$regex": query, "$options": "i"}},
                {"vision.tags": {"$regex": query, "$options": "i"}},
                {"geo.place_name": {"$regex": query, "$options": "i"}},
                {"geo.city": {"$regex": query, "$options": "i"}},
            ]})
        if tag:
            clauses.append({"vision.tags": tag})
        if clauses:
            filters["$and"] = clauses
        cursor = db.photos.find(filters).sort("created_at", -1).limit(min(limit, 20))
        items = [serialize(doc) for doc in await cursor.to_list(20)]
        compact = [
            {
                "id": item.get("id"),
                "filename": item.get("filename"),
                "caption": (item.get("vision") or {}).get("caption"),
                "tags": (item.get("vision") or {}).get("tags"),
                "place": (item.get("geo") or {}).get("place_name") or (item.get("geo") or {}).get("city"),
                "taken_at": (item.get("metadata") or {}).get("taken_at"),
            }
            for item in items if item
        ]
        return json.dumps(compact, ensure_ascii=False)

    @tool
    async def list_albums() -> str:
        """列出用户相册。"""
        cursor = db.albums.find({"user_id": user_id}).sort("updated_at", -1).limit(30)
        albums = [serialize(doc) for doc in await cursor.to_list(30)]
        compact = [{"id": a.get("id"), "name": a.get("name"), "kind": a.get("kind"), "count": len(a.get("photo_ids") or [])} for a in albums if a]
        return json.dumps(compact, ensure_ascii=False)

    @tool
    async def get_journey_summary() -> str:
        """获取按时间排序的行程点摘要。"""
        cursor = db.photos.find(
            {"user_id": user_id, "metadata.lat": {"$ne": None}, "metadata.lng": {"$ne": None}},
        ).sort("metadata.taken_at", 1).limit(80)
        points = []
        async for doc in cursor:
            meta = doc.get("metadata") or {}
            geo = doc.get("geo") or {}
            points.append({
                "id": str(doc["_id"]),
                "taken_at": meta.get("taken_at"),
                "lat": meta.get("lat"),
                "lng": meta.get("lng"),
                "place": geo.get("place_name") or geo.get("city"),
            })
        return json.dumps({"count": len(points), "points": points[:40]}, ensure_ascii=False)

    @tool
    async def get_recommendations(limit: int = 5) -> str:
        """获取最近的地点/天气推荐。"""
        cursor = db.recommendations.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
        items = [serialize(doc) for doc in await cursor.to_list(limit)]
        compact = [{"title": i.get("title"), "body": i.get("body"), "type": i.get("type"), "read": i.get("read")} for i in items if i]
        return json.dumps(compact, ensure_ascii=False)

    return [search_photos, list_albums, get_journey_summary, get_recommendations]


async def run_assistant_agent(state: ChatAgentState) -> ChatAgentState:
    user_id = state["user_id"]
    message = state["message"]
    history = state.get("history") or []

    if not llm_available():
        db = get_db()
        count = await db.photos.count_documents({"user_id": user_id})
        albums = await db.albums.count_documents({"user_id": user_id})
        return {
            **state,
            "reply": f"当前未配置大模型 API Key，我仍可以告诉你：图库有 {count} 张照片、{albums} 个相册。配置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY 后即可对话查询。",
        }

    tools = _tools_for_user(user_id)
    llm = create_agent_llm(
        "agent3",
        model=state.get("model_name"),
        provider=state.get("provider"),
        temperature=0.3,
        vision=False,
    ).bind_tools(tools)

    messages: List[Any] = [SystemMessage(content=ASSISTANT_SYSTEM)]
    for item in history[-8:]:
        role = item.get("role")
        content = item.get("content") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(SystemMessage(content=f"此前助手回复：{content}"))
    messages.append(HumanMessage(content=message))

    try:
        ai_message = await llm.ainvoke(messages)
        messages.append(ai_message)
        if getattr(ai_message, "tool_calls", None):
            tool_node = ToolNode(tools)
            tool_result = await tool_node.ainvoke({"messages": messages})
            messages.extend(tool_result["messages"])
            ai_message = await llm.ainvoke(messages)
        reply = getattr(ai_message, "content", None) or "我暂时没有更多信息。"
    except Exception as exc:
        logger.exception("Assistant agent failed")
        reply = f"助手暂时不可用：{exc}"

    return {**state, "reply": reply}
