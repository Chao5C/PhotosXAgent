from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus, unquote

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from photosx.llm.client import create_agent_llm, extract_json, llm_available

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM = """你是自媒体调研编辑。根据用户选题与检索到的资料，输出严格 JSON（不要 Markdown）：
{
  "hot_score": 1-10,
  "hook": "一句抓人的开场",
  "summary": "80字内摘要",
  "claims": [{"point":"论点","detail":"论据","source_index":0}],
  "cta": "行动号召",
  "risks": ["事实不确定点"],
  "sources_used": [0,1]
}
规则：不得编造具体数字；只能引用资料中的事实；source_index 对应资料列表下标。
"""


async def web_search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """beta：DuckDuckGo HTML 检索；失败时返回空列表，由 LLM 明确标注无联网来源。"""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": "PhotosXAgent-Studio/0.1"}
    items: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
        # result links
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
            html,
            flags=re.S | re.I,
        ):
            href, title, snippet = m.group(1), m.group(2), m.group(3)
            title = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            if "uddg=" in href:
                real = re.search(r"uddg=([^&]+)", href)
                if real:
                    href = unquote(real.group(1))
            if not title:
                continue
            items.append({"title": title, "url": href, "snippet": snippet})
            if len(items) >= limit:
                break
        if not items:
            for m in re.finditer(r'href="(https?://[^"]+)"[^>]*class="result__url"', html):
                items.append({"title": m.group(1), "url": m.group(1), "snippet": ""})
                if len(items) >= limit:
                    break
    except Exception as exc:
        logger.warning("web_search failed: %s", exc)
    return items


async def synthesize_research(topic: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = {
        "hot_score": 5,
        "hook": f"关于「{topic}」，先把能核实的事实摆清楚。",
        "summary": f"围绕「{topic}」整理可引用信息；联网结果 {'有' if sources else '暂无'}。",
        "claims": [
            {
                "point": "先区分事实与观点",
                "detail": sources[0]["snippet"] if sources else "当前未能联网取证，请人工补充资料。",
                "source_index": 0 if sources else None,
            }
        ],
        "cta": "收藏后对照原文再发。",
        "risks": ["联网检索可能不稳定", "请核对来源时效"],
        "sources_used": list(range(min(3, len(sources)))),
        "source": "heuristic",
    }
    if not llm_available():
        return fallback
    try:
        llm = create_agent_llm("agent2", temperature=0.2, vision=False)
        payload = {"topic": topic, "sources": sources}
        resp = await llm.ainvoke(
            [
                SystemMessage(content=RESEARCH_SYSTEM),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)[:8000]),
            ]
        )
        parsed = extract_json(getattr(resp, "content", "") or "")
        if parsed.get("hook") and parsed.get("claims"):
            parsed["source"] = "research_llm"
            return parsed
    except Exception as exc:
        logger.warning("synthesize_research failed: %s", exc)
    return fallback


def build_content_body(topic: str, research: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    lines = [
        f"# {topic}",
        "",
        "## 钩子",
        research.get("hook") or "",
        "",
        "## 摘要",
        research.get("summary") or "",
        "",
        "## 核心论点",
    ]
    for i, claim in enumerate(research.get("claims") or [], 1):
        if isinstance(claim, dict):
            lines.append(f"### {i}. {claim.get('point') or '论点'}")
            lines.append(str(claim.get("detail") or ""))
            idx = claim.get("source_index")
            if isinstance(idx, int) and 0 <= idx < len(sources):
                src = sources[idx]
                lines.append(f"> 来源：{src.get('title')} — {src.get('url')}")
        else:
            lines.append(f"- {claim}")
        lines.append("")
    if research.get("cta"):
        lines.extend(["## 行动号召", str(research["cta"]), ""])
    if research.get("risks"):
        lines.append("## 风险与待核实")
        for r in research["risks"]:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("## 参考来源")
    for i, src in enumerate(sources):
        lines.append(f"{i}. [{src.get('title')}]({src.get('url')}) — {src.get('snippet')}")
    return "\n".join(lines).strip() + "\n"
