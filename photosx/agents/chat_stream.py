from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from app.core.database import get_db
from app.services.analysis_service import AnalysisService
from app.services.poster_service import PosterService
from app.services.session_service import SessionService
from photosx.agents.assistant_agent import (
    ASSISTANT_SYSTEM,
    _compact_history,
    _final_text,
    extract_travel_destination,
    is_person_appearance,
    is_poster_confirm_request,
    is_reparse_request,
    is_travel_advice_request,
)
from photosx.agents.tools.chat_tools import (
    CHAT_TOOLS,
    ChatToolContext,
    reset_chat_tool_context,
    set_chat_tool_context,
)
from photosx.graph.state import ChatAgentState
from photosx.llm.client import create_agent_llm, llm_available

logger = logging.getLogger(__name__)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def stream_chat(state: ChatAgentState) -> AsyncIterator[str]:
    user_id = state["user_id"]
    message = state.get("message") or ""
    history = state.get("history") or []
    photo_ids = [pid for pid in (state.get("photo_ids") or []) if pid]
    top_k = int(state.get("top_k") or 5)
    provider = state.get("provider") or ""
    model_name = state.get("model_name") or ""

    db = get_db()
    sessions = SessionService(db)
    await sessions.touch(user_id)

    if not llm_available():
        count = await db.photos.count_documents({"user_id": user_id})
        albums = await db.albums.count_documents({"user_id": user_id})
        reply = f"当前未配置大模型 API Key。图库有 {count} 张照片、{albums} 个相册。"
        yield _sse({"type": "token", "content": reply})
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": "CHAT",
                "kind": "chat",
                "photos": [],
                "albums": [],
                "total": 0,
                "has_more": False,
                "query_id": "",
            }
        )
        return

    if is_person_appearance(message):
        reply = "我不会评价人物的外貌美丑。如果想了解照片里的场景、地点、天气或内容，我可以继续帮你。"
        yield _sse({"type": "token", "content": reply})
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": "QUESTION",
                "kind": "chat",
                "photos": [],
                "albums": [],
                "total": 0,
                "has_more": False,
                "query_id": "",
            }
        )
        return

    if is_reparse_request(message):
        from app.services.photo_service import PhotoService

        svc = PhotoService(db)
        result = await svc.reanalyze_batch(user_id, include_pending=True, include_failed=True)
        queue = await svc.get_parse_queue(user_id, limit=8)
        queued = result.get("queued") or 0
        analyzing = (queue.get("counts") or {}).get("analyzing") or 0
        if queued:
            reply = f"已提交 {queued} 张未解析/失败的照片重新识别（Agent1）。另有 {analyzing} 张正在识别中，可在图库任务队列查看进度。"
        else:
            active = queue.get("active") or 0
            reply = (
                f"当前没有需要重新提交的排队/失败照片。"
                f"{'另有 ' + str(analyzing) + ' 张正在识别中。' if analyzing else ''}"
                f"{'图库中仍有 ' + str(active) + ' 张待完成。' if active and not analyzing else ''}"
                "你可以在图库页查看解析队列。"
            )
        yield _sse({"type": "token", "content": reply})
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": "COMMAND",
                "kind": "chat",
                "photos": queue.get("items") or [],
                "albums": [],
                "total": queued,
                "has_more": False,
                "query_id": "",
            }
        )
        return

    if is_poster_confirm_request(message, history):
        guide = await sessions.get_last_guide(user_id)
        if not guide:
            guide = AnalysisService(db).guide_from_history(history)
        if not guide:
            reply = "我这边还没有可做成海报的完整攻略。你可以先说「想去上海有什么建议」，生成攻略后再回复「生成海报」。"
            yield _sse({"type": "token", "content": reply})
            yield _sse(
                {
                    "type": "done",
                    "reply": reply,
                    "intent": "POSTER",
                    "kind": "chat",
                    "photos": [],
                    "albums": [],
                    "total": 0,
                    "has_more": False,
                    "query_id": "",
                }
            )
            return
        yield _sse({"type": "status", "content": "正在生成海报图片…"})
        poster = await PosterService(user_id).create_from_guide(db, guide)
        await sessions.clear_poster_offer(user_id)
        reply = f"已生成海报「{poster.get('title') or '出行攻略'}」，已保存到海报图库。"
        yield _sse({"type": "token", "content": reply})
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": "POSTER",
                "kind": "chat",
                "photos": [],
                "albums": [],
                "total": 0,
                "has_more": False,
                "query_id": "",
                "poster": poster,
                "guide": guide,
            }
        )
        return

    if is_travel_advice_request(message):
        destination = extract_travel_destination(message)
        if destination:
            reply = ""
            meta: dict[str, Any] = {}
            async for event in AnalysisService(db).stream_travel_advice(user_id, destination, message):
                if event.get("type") == "status":
                    yield _sse(event)
                elif event.get("type") == "token":
                    reply += event.get("content") or ""
                    yield _sse(event)
                elif event.get("type") == "done":
                    meta = event
                    reply = event.get("reply") or reply
            guide = meta.get("guide") or {}
            if guide:
                await sessions.save_last_guide(user_id, guide)
                await sessions.mark_poster_offer(user_id)
            yield _sse(
                {
                    "type": "done",
                    "reply": reply,
                    "intent": "TRAVEL_ADVICE",
                    "kind": "chat",
                    "photos": [],
                    "albums": [],
                    "total": 0,
                    "has_more": False,
                    "query_id": "",
                    "guide": guide,
                }
            )
            return

    ctx = ChatToolContext(user_id=user_id, top_k=top_k, attached_photo_ids=list(photo_ids))
    token = set_chat_tool_context(ctx)
    reply = ""
    try:
        llm = create_agent_llm(
            "agent3",
            model=model_name or None,
            provider=provider or None,
            temperature=0.3,
            vision=False,
        )
        agent = create_react_agent(llm, CHAT_TOOLS, prompt=ASSISTANT_SYSTEM)
        user_blob = message
        if photo_ids:
            user_blob += f"\n\n[附带照片 id: {photo_ids}]\n[默认 top_k={top_k}]"
        else:
            user_blob += f"\n\n[默认 top_k={top_k}]"
        inputs = {"messages": [*_compact_history(history), HumanMessage(content=user_blob)]}

        async for event in agent.astream_events(inputs, version="v2"):
            if event.get("event") != "on_chat_model_stream":
                continue
            chunk = (event.get("data") or {}).get("chunk")
            if not chunk:
                continue
            content = chunk.content if isinstance(chunk.content, str) else ""
            if not content or getattr(chunk, "tool_calls", None):
                continue
            reply += content
            yield _sse({"type": "token", "content": content})

        if not reply.strip():
            result = await agent.ainvoke(inputs)
            reply = _final_text(result.get("messages") or [])
            if reply:
                yield _sse({"type": "token", "content": reply})

        if photo_ids and not ctx.photos:
            from app.services.rag_service import RagService

            rag = RagService(db)
            photos = await rag.photos_by_ids(user_id, photo_ids)
            ctx.photos = [rag.compact_photo(p) for p in photos[:top_k]]
            ctx.all_ids = [p.get("id") for p in photos if p.get("id")]

        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": ctx.intent,
                "kind": ctx.kind or "chat",
                "photos": ctx.photos or [],
                "albums": ctx.albums or [],
                "total": len(ctx.photos or []),
                "has_more": ctx.search_has_more,
                "query_id": ctx.query_id,
                "reminder": ctx.reminder,
            }
        )
    except Exception as exc:
        logger.exception("stream chat failed")
        reply = f"助手暂时不可用：{exc}"
        yield _sse({"type": "token", "content": reply})
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "intent": "CHAT",
                "kind": "chat",
                "photos": [],
                "albums": [],
                "total": 0,
                "has_more": False,
                "query_id": "",
            }
        )
    finally:
        reset_chat_tool_context(token)
