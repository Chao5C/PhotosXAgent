from __future__ import annotations

import logging
import re

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from app.core.database import get_db
from app.services.poster_service import PosterService
from app.services.analysis_service import AnalysisService
from app.services.rag_service import RagService
from app.services.session_service import SessionService
from photosx.agents.tools.chat_tools import (
    CHAT_TOOLS,
    ChatToolContext,
    reset_chat_tool_context,
    set_chat_tool_context,
)
from photosx.graph.state import ChatAgentState
from photosx.llm.client import create_agent_llm, llm_available

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM = """你是 PhotosXAgent 的 ChatAgent。用简洁中文帮助用户管理照片与相册。

## 硬性规则
1. 禁止编造不存在的照片/相册；只能引用工具返回的 id 与字段。
2. 用户询问人物美丑、颜值、漂不漂亮、帅不帅、好看吗（针对人物）时：直接拒绝评价，不要调用工具去分析外貌。
3. 回答可引用 photo_id / album_id，前端会展示缩略图。
4. 修改偏好、静音推送、定时提醒后，必须调用对应工具并确认已写入，口头答应不算完成。

## 工具使用策略
- 搜索多张照片 → search_photos_short（只用短标签向量检索）。
- 搜索相册/合集 → search_albums。
- 用户要查看更多 → get_search_page（使用已有 query_id）。
- 追问单张/少量照片细节、人物是谁、拍的什么 → 有 photo_id 则 load_photo_long；没有则先 short 检索再加载长描述（最多 3 张）。
- 问地点 → get_photo_geo；问天气/气温/穿衣 → get_weather。
- 用户说想去某地、计划旅行、问出行/游玩建议或攻略（如「想去上海有什么建议」）→ travel_advice。**禁止**用 search_photos_short 按地名搜照片来回答这类问题。
- 用户要把攻略做成海报/一张图/分享图 → 直接说明会整合最近完整攻略生成海报（系统会自动处理）。
- 整合/分析指定照片（行程/RAG）→ analyze_photos。
- **重新解析未识别/失败的照片**（pending/failed，Agent1 识图）→ reparse_photos。用户说「解析未解析的图片」「重新识别失败的照片」时必须用这个，不要用 analyze_photos。
- 主动要推送攻略 → push_guide(force=true)。
- 停止某类推送 → mute_topic；设置提醒 → add_reminder；记住偏好 → add_memory_fact。

## 检索规范
1. 主检索只用 short chunk；首次回复默认只展示 top_k（通常 5）张。
2. 用户明确要求某类照片（如「宠物照」「必须是宠物」「只要风景」）时，search_photos_short 会严格按 scene_type 过滤，禁止混入其他场景。
3. 首次检索不要做全量索引，也不要在回复里编造「共匹配 N 条」——工具返回的 total 只是当前展示数量。
4. 只有用户明确说「查看更多」时才调用 get_search_page；该调用会建立完整索引并分页。
5. 长 chunk 仅在追问细节时按 ID 加载，禁止对大批量结果一次性 load_photo_long。

## 回复
先完成必要工具调用，再基于结果用 2–6 句中文回答。工具失败时说明原因，不要编造。
"""

APPEARANCE_WORDS = ("美丑", "颜值", "漂不漂亮", "漂亮吗", "帅不帅", "难看", "丑不丑", "好不好看", "好看吗", "美吗", "丑吗")
PERSON_WORDS = ("人", "她", "他", "谁", "人物", "脸", "长相")
REPARSE_HINTS = ("未解析", "没解析", "未识别", "没识别", "解析失败", "识别失败", "失败的照片", "没分析")
REPARSE_ACTIONS = ("解析", "识别", "分析", "重试", "重新")
TRAVEL_ADVICE_HINTS = ("想去", "打算去", "计划去", "准备去", "要去", "出行", "游玩", "旅游", "旅行")
TRAVEL_ADVICE_ASKS = ("建议", "推荐", "攻略", "怎么玩", "有什么", "玩什么", "去哪", "吃什么", "怎么安排", "行程安排")
PHOTO_SEARCH_OVERRIDES = ("找", "搜索", "查", "照片", "图片", "相册", "哪些", "有没有", "我拍的", "给我看", "找出来")
POSTER_ACTION_HINTS = (
    "生成海报",
    "做成海报",
    "做海报",
    "转成海报",
    "导出海报",
    "生成一张海报",
    "做成一张海报",
    "出海报",
    "制作海报",
)
POSTER_SHORT_CONFIRMS = ("好", "好的", "可以", "要", "是的", "行", "嗯", "生成", "做")
POSTER_NEGATION = ("不要", "不用", "不需要", "先不", "别")


def is_reparse_request(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if any(h in text for h in REPARSE_HINTS):
        return True
    if ("重新" in text or "再" in text or "把" in text) and any(a in text for a in REPARSE_ACTIONS):
        if any(w in text for w in ("图片", "照片", "图库", "这些", "全部", "所有")):
            return True
    if "将" in text and any(a in text for a in REPARSE_ACTIONS) and any(w in text for w in ("图片", "照片", "未解析")):
        return True
    return False


def is_travel_advice_request(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if any(h in text for h in PHOTO_SEARCH_OVERRIDES):
        if not any(h in text for h in TRAVEL_ADVICE_HINTS) and not re.search(r"去[\u4e00-\u9fff]{1,8}", text):
            return False
    has_travel = any(h in text for h in TRAVEL_ADVICE_HINTS) or bool(re.search(r"去[\u4e00-\u9fff]{1,8}", text))
    has_ask = any(h in text for h in TRAVEL_ADVICE_ASKS)
    return has_travel and has_ask


def extract_travel_destination(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    patterns = (
        r"(?:最近)?(?:想|打算|计划|准备)?去([\u4e00-\u9fff]{2,8}?)(?:[，,。！？?]|有什么|怎么|玩|旅游|旅行|$)",
        r"到([\u4e00-\u9fff]{2,8}?)(?:[，,。！？?]|有什么|怎么|玩|旅游|旅行|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        dest = match.group(1).strip()
        for suffix in ("有什么", "怎么", "吗", "呢", "吧", "的", "旅游", "旅行"):
            if dest.endswith(suffix):
                dest = dest[: -len(suffix)]
        dest = dest.strip("，。！？? ")
        if len(dest) >= 2:
            return dest
    return ""


def is_poster_confirm_request(message: str, history: list | None = None) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if any(n in text for n in POSTER_NEGATION):
        return False
    if any(h in text for h in POSTER_ACTION_HINTS):
        return True
    last_assistant = ""
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            last_assistant = item.get("content") or ""
            break
    asked_poster = "海报" in last_assistant and ("生成" in last_assistant or "做成" in last_assistant or "？" in last_assistant or "?" in last_assistant)
    if asked_poster and len(text) <= 8 and any(text.startswith(c) or text == c for c in POSTER_SHORT_CONFIRMS):
        return True
    return False


def is_poster_request(message: str) -> bool:
    return is_poster_confirm_request(message)


def is_person_appearance(message: str) -> bool:
    text = message or ""
    if not any(word in text for word in APPEARANCE_WORDS):
        return False
    return any(word in text for word in PERSON_WORDS) or "颜值" in text or "美丑" in text


def _compact_history(history: list) -> list:
    messages = []
    for item in history[-8:]:
        role = item.get("role")
        content = (item.get("content") or "")[:500]
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _final_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str) and content.strip() and not msg.tool_calls:
                return content.strip()
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                text = "".join(parts).strip()
                if text and not msg.tool_calls:
                    return text
    return "我没有理解这个问题。"


async def run_assistant_agent(state: ChatAgentState) -> ChatAgentState:
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
        return {
            **state,
            "reply": f"当前未配置大模型 API Key。图库有 {count} 张照片、{albums} 个相册。",
            "intent": "CHAT",
            "photos": [],
        }

    if is_person_appearance(message):
        return {
            **state,
            "reply": "我不会评价人物的外貌美丑。如果想了解照片里的场景、地点、天气或内容，我可以继续帮你。",
            "intent": "QUESTION",
            "photos": [],
            "albums": [],
            "total": 0,
            "kind": "chat",
        }

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
        return {
            **state,
            "reply": reply,
            "intent": "COMMAND",
            "photos": queue.get("items") or [],
            "albums": [],
            "total": queued,
            "kind": "chat",
        }

    if is_poster_confirm_request(message, history):
        guide = await sessions.get_last_guide(user_id)
        if not guide:
            guide = AnalysisService(db).guide_from_history(history)
        if not guide:
            return {
                **state,
                "reply": "我这边还没有可做成海报的完整攻略。你可以先说「想去上海有什么建议」，生成攻略后再回复「生成海报」。",
                "intent": "POSTER",
                "photos": [],
                "albums": [],
                "total": 0,
                "kind": "chat",
            }
        poster = await PosterService(user_id).create_from_guide(db, guide)
        await sessions.clear_poster_offer(user_id)
        reply = f"已生成海报「{poster.get('title') or '出行攻略'}」，已保存到海报图库。"
        return {
            **state,
            "reply": reply,
            "intent": "POSTER",
            "photos": [],
            "albums": [],
            "total": 0,
            "kind": "chat",
            "poster": poster,
            "guide": guide,
        }

    if is_travel_advice_request(message):
        destination = extract_travel_destination(message)
        if destination:
            result = await AnalysisService(db).travel_advice_for_place(user_id, destination, message)
            await sessions.mark_poster_offer(user_id)
            return {
                **state,
                "reply": result.get("reply") or "暂时无法生成出行建议，请稍后再试。",
                "intent": "TRAVEL_ADVICE",
                "photos": [],
                "albums": [],
                "total": 0,
                "kind": "chat",
                "guide": result.get("guide"),
            }

    ctx = ChatToolContext(user_id=user_id, top_k=top_k, attached_photo_ids=list(photo_ids))
    token = set_chat_tool_context(ctx)
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

        result = await agent.ainvoke({"messages": [*_compact_history(history), HumanMessage(content=user_blob)]})
        reply = _final_text(result.get("messages") or [])

        if photo_ids and not ctx.photos:
            rag = RagService(db)
            photos = await rag.photos_by_ids(user_id, photo_ids)
            ctx.photos = [rag.compact_photo(p) for p in photos[:top_k]]
            ctx.all_ids = [p.get("id") for p in photos if p.get("id")]

        return {
            **state,
            "reply": reply,
            "intent": ctx.intent,
            "photos": ctx.photos or [],
            "albums": ctx.albums or [],
            "total": len(ctx.photos or []),
            "has_more": ctx.search_has_more,
            "query_id": ctx.query_id,
            "kind": ctx.kind or "chat",
            "reminder": ctx.reminder,
        }
    except Exception as exc:
        logger.exception("ChatAgent tool loop failed")
        return {**state, "reply": f"助手暂时不可用：{exc}", "intent": "CHAT", "photos": []}
    finally:
        reset_chat_tool_context(token)
