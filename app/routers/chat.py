from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.utils.serialize import utcnow
from photosx.graph.chat_graph import chat_graph
from photosx.llm.client import persist_agent_models, refresh_runtime

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    provider: str | None = None
    model_name: str | None = None


@router.post("")
async def chat(payload: ChatRequest, user=Depends(get_current_user)):
    db = get_db()
    user_id = str(user["_id"])
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
        }
    )
    reply = result.get("reply") or "我没有理解这个问题。"
    now = utcnow()
    await db.chat_messages.insert_many(
        [
            {"user_id": user_id, "role": "user", "content": payload.message, "created_at": now},
            {"user_id": user_id, "role": "assistant", "content": reply, "created_at": now},
        ]
    )
    return ok({"reply": reply})


@router.get("/history")
async def chat_history(user=Depends(get_current_user)):
    db = get_db()
    cursor = db.chat_messages.find({"user_id": str(user["_id"])}).sort("created_at", 1).limit(80)
    items = [
        {"role": d.get("role"), "content": d.get("content"), "created_at": d.get("created_at").isoformat() if d.get("created_at") else None}
        for d in await cursor.to_list(80)
    ]
    return ok(items)
