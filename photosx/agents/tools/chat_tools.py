from __future__ import annotations

import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from langchain_core.tools import tool

from app.core.database import get_db
from app.services.analysis_service import AnalysisService
from app.services.geo_service import fetch_weather
from app.services.rag_service import RagService, infer_scene_filter
from app.services.session_service import SessionService
from app.utils.serialize import serialize, utcnow

_ctx: ContextVar[Optional["ChatToolContext"]] = ContextVar("chat_tool_ctx", default=None)


@dataclass
class ChatToolContext:
    user_id: str
    top_k: int = 5
    attached_photo_ids: list[str] = field(default_factory=list)
    photos: list[dict] = field(default_factory=list)
    albums: list[dict] = field(default_factory=list)
    all_ids: list[str] = field(default_factory=list)
    all_albums: list[dict] = field(default_factory=list)
    query_id: str = ""
    intent: str = "CHAT"
    kind: str = "chat"
    memory: dict | None = None
    reminder: dict | None = None
    search_has_more: bool = False


def set_chat_tool_context(ctx: ChatToolContext):
    return _ctx.set(ctx)


def reset_chat_tool_context(token) -> None:
    _ctx.reset(token)


def get_ctx() -> ChatToolContext:
    ctx = _ctx.get()
    if ctx is None:
        raise RuntimeError("ChatToolContext 未初始化")
    return ctx


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _mark_intent(intent: str, kind: str | None = None) -> None:
    ctx = get_ctx()
    ctx.intent = intent
    if kind:
        ctx.kind = kind


def _parse_fire_at(text: str) -> datetime:
    now = utcnow()
    blob = (text or "").strip().lower()
    if not blob:
        return now + timedelta(hours=2)
    base = now + timedelta(days=1) if "明天" in blob else now
    match = re.search(r"(\d{1,2})点", blob)
    if match:
        return base.replace(hour=int(match.group(1)), minute=0, second=0, microsecond=0)
    for pattern, unit in (
        (r"(\d+)\s*(?:秒|s)(?:钟)?(?:后)?", "seconds"),
        (r"(\d+)\s*分钟后", "minutes"),
        (r"(\d+)\s*小时后", "hours"),
        (r"(\d+)\s*天后", "days"),
    ):
        m = re.search(pattern, blob)
        if not m:
            continue
        amount = int(m.group(1))
        if unit == "seconds":
            return now + timedelta(seconds=max(amount, 1))
        if unit == "minutes":
            return now + timedelta(minutes=amount)
        if unit == "hours":
            return now + timedelta(hours=amount)
        return now + timedelta(days=amount)
    return now + timedelta(hours=2)


def _reminder_payload(item: dict) -> dict:
    fire_at = item.get("fire_at")
    if isinstance(fire_at, datetime):
        fire_at = fire_at.isoformat()
    return {
        "id": item.get("id"),
        "text": item.get("text") or "",
        "fire_at": fire_at,
    }


async def _persist_search(
    query: str,
    photo_ids: list[str],
    albums: list[dict],
    *,
    scene_type: str | None = None,
    indexed: bool = False,
) -> str:
    ctx = get_ctx()
    db = get_db()
    stored = {
        "user_id": ctx.user_id,
        "photo_ids": photo_ids,
        "albums": albums,
        "query": query,
        "scene_type": scene_type,
        "indexed": indexed,
        "created_at": utcnow(),
    }
    inserted = await db.chat_searches.insert_one(stored)
    ctx.query_id = str(inserted.inserted_id)
    ctx.all_ids = photo_ids
    ctx.all_albums = albums
    return ctx.query_id


async def _ensure_search_indexed(doc: dict) -> list[str]:
    return await RagService(get_db()).ensure_chat_search_indexed(doc)


async def _search_albums(user_id: str, query: str) -> list[dict]:
    db = get_db()
    cursor = db.albums.find({"user_id": user_id}).sort("updated_at", -1).limit(30)
    albums = [serialize(doc) for doc in await cursor.to_list(30) if doc]
    q = (query or "").lower()
    matched: list[dict] = []
    for album in albums:
        blob = f"{album.get('name') or ''} {album.get('kind') or ''} {album.get('location') or ''}".lower()
        tokens = [t for t in re.split(r"[\s,，]+", q) if len(t) >= 2]
        if q and "相册" not in q and "合集" not in q:
            if not any(token in blob for token in tokens):
                continue
        matched.append(
            {
                "id": album.get("id"),
                "name": album.get("name"),
                "kind": album.get("kind"),
                "count": len(album.get("photo_ids") or []),
                "photo_ids": album.get("photo_ids") or [],
            }
        )
    if not matched and ("相册" in (query or "") or "合集" in (query or "")):
        matched = [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "kind": a.get("kind"),
                "count": len(a.get("photo_ids") or []),
                "photo_ids": a.get("photo_ids") or [],
            }
            for a in albums[:8]
        ]
    return matched


@tool
async def search_photos_short(query: str, top_k: int = 0, scene_type: str = "") -> str:
    """用短标签 chunk 做向量检索，返回候选照片 ID 与摘要卡片。搜索多张照片/合集时使用。不要用此工具加载长描述。
    若用户明确要求某类照片（如宠物照/风景照），必须传入 scene_type 或让 query 含类型词，结果会严格过滤。"""
    ctx = get_ctx()
    _mark_intent("QUERY")
    k = top_k or ctx.top_k or 5
    scene = (scene_type or "").strip() or infer_scene_filter(query)
    rag = RagService(get_db())
    ids = await rag.search_short(
        ctx.user_id,
        query,
        top_k=k,
        scene_type=scene,
        extra_ids=ctx.attached_photo_ids,
    )
    photos = await rag.photos_by_ids(ctx.user_id, ids)
    compact = [rag.compact_photo(p) for p in photos]
    shown = compact[:k]
    shown_ids = [p.get("id") for p in shown if p.get("id")]
    query_id = await _persist_search(
        query,
        shown_ids,
        [],
        scene_type=scene,
        indexed=False,
    )
    ctx.photos = shown
    ctx.all_ids = shown_ids
    ctx.search_has_more = len(shown_ids) >= k
    return _json(
        {
            "photos": shown,
            "total": len(shown_ids),
            "shown": len(shown_ids),
            "has_more": ctx.search_has_more,
            "indexed": False,
            "scene_type": scene,
            "all_ids": shown_ids,
            "query_id": query_id,
            "hint": "默认只展示 top_k 条；完整检索在用户点击查看更多时再建立索引。",
        }
    )


@tool
async def search_albums(query: str, top_k: int = 0) -> str:
    """按名称/类型/地点搜索相册或合集。用户提到相册、合集、专辑时使用。"""
    ctx = get_ctx()
    _mark_intent("QUERY")
    k = top_k or ctx.top_k or 5
    albums = await _search_albums(ctx.user_id, query)
    shown = albums[:k]
    ids: list[str] = []
    for album in albums:
        for pid in album.get("photo_ids") or []:
            if pid not in ids:
                ids.append(pid)
    query_id = await _persist_search(query, ids, albums)
    ctx.albums = shown
    ctx.photos = ctx.photos or []
    if ids and not ctx.photos:
        rag = RagService(get_db())
        photos = await rag.photos_by_ids(ctx.user_id, ids[:k])
        ctx.photos = [rag.compact_photo(p) for p in photos]
    return _json({"albums": shown, "total_albums": len(albums), "photo_ids": ids[:40], "query_id": query_id})


@tool
async def get_search_page(query_id: str, offset: int = 0, limit: int = 5) -> str:
    """根据已有 query_id 分页查看更多检索结果。仅在用户明确说「查看更多」时调用。"""
    ctx = get_ctx()
    _mark_intent("QUERY")
    db = get_db()
    from bson import ObjectId

    try:
        doc = await db.chat_searches.find_one({"_id": ObjectId(query_id), "user_id": ctx.user_id})
    except Exception:
        doc = None
    if not doc:
        return _json({"error": "检索结果不存在"})
    ids = await _ensure_search_indexed(doc)
    page_ids = ids[offset : offset + limit]
    rag = RagService(db)
    photos = [rag.compact_photo(p) for p in await rag.photos_by_ids(ctx.user_id, page_ids)]
    ctx.photos = photos
    ctx.query_id = query_id
    ctx.all_ids = ids
    ctx.search_has_more = offset + limit < len(ids)
    return _json(
        {
            "photos": photos,
            "albums": doc.get("albums") or [],
            "total": len(ids),
            "offset": offset,
            "has_more": ctx.search_has_more,
            "indexed": True,
            "query_id": query_id,
        }
    )


@tool
async def load_photo_long(photo_ids: list[str]) -> str:
    """按照片 ID 加载长描述 chunk，用于咨询单张/少量照片细节。一次最多 3 张。禁止对大批量结果调用。"""
    ctx = get_ctx()
    _mark_intent("QUESTION")
    ids = [pid for pid in (photo_ids or []) if pid][:3]
    if not ids and ctx.attached_photo_ids:
        ids = ctx.attached_photo_ids[:1]
    if not ids:
        return _json({"error": "缺少 photo_id，请先 search_photos_short 或让用户指定照片"})
    rag = RagService(get_db())
    long_map = await rag.load_long_many(ctx.user_id, ids)
    photos = await rag.photos_by_ids(ctx.user_id, ids)
    compact = [rag.compact_photo(p) for p in photos]
    ctx.photos = compact
    ctx.all_ids = ids
    return _json({"long_chunks": long_map, "photos": compact})


@tool
async def get_photo_geo(photo_id: str) -> str:
    """查询单张照片的地点信息（place_name/city/country）。用户问在哪、地点时使用。"""
    ctx = get_ctx()
    _mark_intent("QUESTION")
    rag = RagService(get_db())
    photos = await rag.photos_by_ids(ctx.user_id, [photo_id])
    if not photos:
        return _json({"error": "照片不存在"})
    photo = photos[0]
    geo = photo.get("geo") or {}
    ctx.photos = [rag.compact_photo(photo)]
    return _json(
        {
            "photo_id": photo_id,
            "geo": {k: geo.get(k) for k in ("place_name", "city", "country", "display_name")},
        }
    )


@tool
async def get_weather(photo_id: str = "", lat: float = 0.0, lng: float = 0.0) -> str:
    """查询天气。可传 photo_id（优先用照片 GPS），或直接传 lat/lng。用户问天气、气温、穿衣时使用。"""
    ctx = get_ctx()
    _mark_intent("QUESTION")
    place = None
    weather = None
    if photo_id:
        rag = RagService(get_db())
        photos = await rag.photos_by_ids(ctx.user_id, [photo_id])
        if not photos:
            return _json({"error": "照片不存在"})
        photo = photos[0]
        geo = photo.get("geo") or {}
        meta = photo.get("metadata") or {}
        place = geo.get("place_name") or geo.get("city")
        weather = geo.get("weather")
        lat = float(meta.get("lat") or lat or 0)
        lng = float(meta.get("lng") or lng or 0)
        ctx.photos = [rag.compact_photo(photo)]
    if weather is None and lat and lng:
        weather = await fetch_weather(lat, lng)
    if weather is None:
        return _json({"error": "无法获取天气，缺少有效坐标"})
    return _json({"photo_id": photo_id or None, "place": place, "weather": weather, "lat": lat, "lng": lng})


@tool
async def reparse_photos(include_pending: bool = True, include_failed: bool = True) -> str:
    """重新解析未完成的图片：排队中(pending)与解析失败(failed)的照片会重新提交 Agent1 视觉识别。
    用户说「解析未解析的图片」「重新解析失败的照片」「把没识别的图再识别一遍」时使用。
    不要与 analyze_photos 混淆——后者是行程/RAG 整合分析，不会重新识图。"""
    ctx = get_ctx()
    _mark_intent("COMMAND")
    from app.services.photo_service import PhotoService

    result = await PhotoService(get_db()).reanalyze_batch(
        ctx.user_id,
        include_pending=include_pending,
        include_failed=include_failed,
    )
    queue = await PhotoService(get_db()).get_parse_queue(ctx.user_id, limit=10)
    ctx.photos = queue.get("items") or []
    return _json({"ok": True, "reparse": result, "queue": queue})


@tool
async def travel_advice(destination: str, question: str = "") -> str:
    """用户询问想去某地、计划旅行、出行/游玩建议或攻略时使用。不要用于搜索照片。destination 为目的地，如「上海」。"""
    ctx = get_ctx()
    _mark_intent("TRAVEL_ADVICE", kind="chat")
    ctx.photos = []
    ctx.all_ids = []
    result = await AnalysisService(get_db()).travel_advice_for_place(
        ctx.user_id,
        destination,
        question or destination,
    )
    return _json(result)


@tool
async def analyze_photos(photo_ids: list[str] | None = None, request_text: str = "") -> str:
    """整合/分析指定照片并入库。用户说整合、分析这些、汇总这些照片时使用。"""
    ctx = get_ctx()
    _mark_intent("QUERY")
    ids = photo_ids or ctx.attached_photo_ids or None
    analysis = await AnalysisService(get_db()).analyze(ctx.user_id, ids, request_text)
    rag = RagService(get_db())
    photos = await rag.photos_by_ids(ctx.user_id, analysis.get("photo_ids") or ids or [])
    compact = [rag.compact_photo(p) for p in photos]
    ctx.photos = compact[: ctx.top_k]
    ctx.all_ids = [p.get("id") for p in compact if p.get("id")]
    if ctx.all_ids:
        await _persist_search(request_text or "analyze", ctx.all_ids, [])
    return _json({"analysis": analysis, "photos": ctx.photos, "total": len(compact)})


@tool
async def push_guide(photo_ids: list[str] | None = None, force: bool = True) -> str:
    """用户主动要求推送攻略/行程建议时调用。force=true 跳过定时器与会话静默，立即返回攻略内容。"""
    ctx = get_ctx()
    _mark_intent("REQUEST_PUSH", kind="push")
    result = await AnalysisService(get_db()).push(
        ctx.user_id,
        photo_ids=photo_ids or ctx.attached_photo_ids or None,
        force=force,
    )
    payload = result.get("payload") or {}
    ctx.photos = payload.get("photos") or []
    ctx.all_ids = payload.get("photo_ids") or []
    return _json(result)


@tool
async def mute_topic(topic: str, mute: bool = True) -> str:
    """停止或恢复某类推送。topic 常用：travel/food/weather/reminder。用户说不要再推、停止推送时使用。"""
    ctx = get_ctx()
    _mark_intent("COMMAND")
    topic = (topic or "travel").strip().lower() or "travel"
    memory = await SessionService(get_db()).mute_topic(ctx.user_id, topic, mute)
    ctx.memory = memory
    return _json({"ok": True, "topic": topic, "muted": mute, "memory": memory})


@tool
async def add_reminder(text: str, fire_at_hint: str = "") -> str:
    """设置定时提醒。text 为提醒内容；fire_at_hint 可含「30秒后」「明天8点」「2小时后」等。用户说提醒我…时使用。"""
    ctx = get_ctx()
    _mark_intent("COMMAND", kind="reminder")
    hint = fire_at_hint or text
    fire_at = _parse_fire_at(hint)
    reminder_text = (text or "").strip() or "提醒"
    item = await SessionService(get_db()).add_reminder(ctx.user_id, reminder_text, fire_at)
    ctx.reminder = _reminder_payload(item)
    ctx.memory = await SessionService(get_db()).get_memory(ctx.user_id)
    return _json({"ok": True, "reminder": ctx.reminder})


@tool
async def add_memory_fact(fact: str) -> str:
    """写入用户长期偏好/事实记忆。用户说记住、以后、我喜欢、我讨厌时使用。"""
    ctx = get_ctx()
    _mark_intent("COMMAND")
    memory = await SessionService(get_db()).add_fact(ctx.user_id, fact)
    ctx.memory = memory
    return _json({"ok": True, "memory": memory})


@tool
async def get_memory() -> str:
    """读取当前用户记忆（facts、静音主题、提醒）。回答偏好相关问题前可调用。"""
    ctx = get_ctx()
    memory = await SessionService(get_db()).get_memory(ctx.user_id)
    ctx.memory = memory
    return _json(memory)


CHAT_TOOLS = [
    travel_advice,
    search_photos_short,
    search_albums,
    get_search_page,
    load_photo_long,
    get_photo_geo,
    get_weather,
    reparse_photos,
    analyze_photos,
    push_guide,
    mute_topic,
    add_reminder,
    add_memory_fact,
    get_memory,
]
