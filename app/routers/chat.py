from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.rag_service import RagService
from app.services.session_service import SessionService
from app.utils.serialize import utcnow
from photosx.agents.chat_stream import stream_chat
from photosx.graph.chat_graph import chat_graph
from photosx.llm.client import persist_agent_models, refresh_runtime

router = APIRouter(prefix="/api/chat", tags=["chat"])

#意图分类 → 分发到固定 handler
class ChatRequest(BaseModel):
    message: str = ""
    provider: str | None = None
    model_name: str | None = None
    photo_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    #topk默认值为5
    query_id: str | None = None
    view_more: bool = False
    offset: int = 0


def _poster_for_storage(poster: dict | None) -> dict | None:
    if not poster:
        return None
    return {k: v for k, v in poster.items() if k != "image_data_url"}


def _history_item(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")) if doc.get("_id") else doc.get("id"),
        "role": doc.get("role"),
        "content": doc.get("content"),
        "kind": doc.get("kind") or "chat",
        "intent": doc.get("intent"),
        "photos": doc.get("photos") or [],
        "albums": doc.get("albums") or [],
        "total": doc.get("total"),
        "has_more": doc.get("has_more"),
        "query_id": doc.get("query_id"),
        "photo_ids": doc.get("photo_ids") or [],
        "reminder": doc.get("reminder"),
        "poster": doc.get("poster"),
        "guide": doc.get("guide"),
        "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
    }


@router.post("")
async def chat(payload: ChatRequest, user=Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    if payload.view_more and payload.query_id:
        return ok(await _search_page(db, user_id, payload.query_id, payload.offset, payload.top_k or 5))

    cursor = db.chat_messages.find({"user_id": user_id}).sort("created_at", -1).limit(12)
    history_docs = list(reversed(await cursor.to_list(12)))
    history = [{"role": d.get("role"), "content": d.get("content")} for d in history_docs]

    if payload.provider and payload.model_name:
        await persist_agent_models(
            {"agent3": {"provider": payload.provider, "model_name": payload.model_name}}
        )
        await refresh_runtime()

    result = await chat_graph.ainvoke(
        {
            "user_id": user_id,
            "message": payload.message,
            "history": history,
            "provider": payload.provider or "",
            "model_name": payload.model_name or "",
            "photo_ids": payload.photo_ids or [],
            "top_k": payload.top_k or 5,
        }
    )
    reply = result.get("reply") or "我没有理解这个问题。"
    now = utcnow()
    photos = result.get("photos") or []
    albums = result.get("albums") or []
    total = result.get("total") or 0
    has_more = result.get("has_more") or False
    query_id = result.get("query_id") or ""
    intent = result.get("intent") or ""
    kind = result.get("kind") or "chat"
    reminder = result.get("reminder")
    poster = result.get("poster")
    guide = result.get("guide")
    await db.chat_messages.insert_many(
        [
            {
                "user_id": user_id,
                "role": "user",
                "content": payload.message,
                "photo_ids": payload.photo_ids or [],
                "kind": "chat",
                "created_at": now,
            },
            {
                "user_id": user_id,
                "role": "assistant",
                "content": reply,
                "kind": kind,
                "intent": intent,
                "photos": photos,
                "albums": albums,
                "total": total,
                "query_id": query_id,
                "has_more": result.get("has_more") or False,
                "reminder": reminder,
                "poster": _poster_for_storage(poster),
                "guide": guide,
                "created_at": now,
            },
        ]
    )
    return ok(
        {
            "reply": reply,
            "intent": intent,
            "kind": kind,
            "photos": photos,
            "albums": albums,
            "total": total,
            "has_more": result.get("has_more") or False,
            "query_id": query_id,
            "reminder": reminder,
            "poster": poster,
            "guide": guide,
        }
    )


@router.post("/stream")
async def chat_stream(payload: ChatRequest, user=Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
    if payload.view_more and payload.query_id:
        page = await _search_page(db, user_id, payload.query_id, payload.offset, payload.top_k or 5)
        async def once():
            import json

            yield f"data: {json.dumps({'type': 'done', **page}, ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(once(), media_type="text/event-stream")

    cursor = db.chat_messages.find({"user_id": user_id}).sort("created_at", -1).limit(12)
    history_docs = list(reversed(await cursor.to_list(12)))
    history = [{"role": d.get("role"), "content": d.get("content")} for d in history_docs]

    if payload.provider and payload.model_name:
        await persist_agent_models(
            {"agent3": {"provider": payload.provider, "model_name": payload.model_name}}
        )
        await refresh_runtime()

    async def persist_and_stream():
        events: list[dict] = []
        final: dict = {}
        async for chunk in stream_chat(
            {
                "user_id": user_id,
                "message": payload.message,
                "history": history,
                "provider": payload.provider or "",
                "model_name": payload.model_name or "",
                "photo_ids": payload.photo_ids or [],
                "top_k": payload.top_k or 5,
            }
        ):
            yield chunk
            if not chunk.startswith("data: "):
                continue
            try:
                import json

                event = json.loads(chunk[6:].strip())
            except Exception:
                continue
            events.append(event)
            if event.get("type") == "done":
                final = event

        if not final:
            return
        now = utcnow()
        reply = final.get("reply") or ""
        await db.chat_messages.insert_many(
            [
                {
                    "user_id": user_id,
                    "role": "user",
                    "content": payload.message,
                    "photo_ids": payload.photo_ids or [],
                    "kind": "chat",
                    "created_at": now,
                },
                {
                    "user_id": user_id,
                    "role": "assistant",
                    "content": reply,
                    "kind": final.get("kind") or "chat",
                    "intent": final.get("intent") or "",
                    "photos": final.get("photos") or [],
                    "albums": final.get("albums") or [],
                    "total": final.get("total") or 0,
                    "query_id": final.get("query_id") or "",
                    "has_more": final.get("has_more") or False,
                    "reminder": final.get("reminder"),
                    "poster": _poster_for_storage(final.get("poster")),
                    "guide": final.get("guide"),
                    "created_at": now,
                },
            ]
        )

    return StreamingResponse(persist_and_stream(), media_type="text/event-stream")


@router.get("/history")
async def chat_history(user=Depends(get_current_user)):
    """获取当前用户的聊天历史记录（按时间升序，最多 80 条）。"""
    db = get_db()
    # 按创建时间升序查询该用户的消息，限制返回数量
    cursor = db.chat_messages.find({"user_id": str(user["_id"])}).sort("created_at", 1).limit(80)
    return ok([_history_item(d) for d in await cursor.to_list(80)])


@router.get("/inbox")
async def chat_inbox(since: str | None = None, user=Depends(get_current_user)):
    db = get_db()
    parsed = None
    if since:
        try:
            parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    items = await SessionService(db).inbox_since(str(user["_id"]), parsed, kinds=["push", "reminder"])
    return ok(items)


@router.get("/search/{query_id}")
async def chat_search(
    query_id: str,
    offset: int = 0,
    limit: int = Query(default=5, le=50),
    user=Depends(get_current_user),
):
    db = get_db()
    return ok(await _search_page(db, str(user["_id"]), query_id, offset, limit))


@router.post("/upload")
async def chat_upload(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    service = PhotoService(get_db())
    items = []
    errors = []
    for upload in files:
        try:
            items.append(await service.save_upload(str(user["_id"]), upload))
        except Exception as exc:
            errors.append({"filename": upload.filename, "error": str(exc)})
    return ok({"items": items, "errors": errors})


async def _search_page(db, user_id: str, query_id: str, offset: int, limit: int) -> dict:
    try:
        doc = await db.chat_searches.find_one({"_id": ObjectId(query_id), "user_id": user_id})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(status_code=404, detail="检索结果不存在")
    rag = RagService(db)
    ids = await rag.ensure_chat_search_indexed(doc)
    albums = doc.get("albums") or []
    page_ids = ids[offset : offset + limit]
    photos = [rag.compact_photo(p) for p in await rag.photos_by_ids(user_id, page_ids)]
    return {
        "photos": photos,
        "albums": albums,
        "total": len(ids),
        "query_id": query_id,
        "offset": offset,
        "has_more": offset + limit < len(ids),
        "indexed": True,
    }
