"""Thin runtime adapters: inject GitHub skill instructions into LLM calls.

Does not reimplement humanizer / html-ppt / video-podcast-maker logic.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from photosx.llm.client import create_agent_llm, llm_available
from photosx.studio.skill_loader import (
    load_skill_md,
    load_skill_ref,
    read_html_ppt_template,
    rewrite_html_ppt_asset_hrefs,
    skill_dir,
)

logger = logging.getLogger(__name__)


def _extract_fenced(text: str, lang_hint: Optional[str] = None) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    pattern = rf"```(?:{lang_hint})\s*\n(.*?)```" if lang_hint else r"```(?:\w+)?\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # bare html document
    if "<!DOCTYPE" in text.upper() or text.lstrip().startswith("<html"):
        start = text.upper().find("<!DOCTYPE")
        if start < 0:
            start = text.lower().find("<html")
        return text[start:].strip()
    return text


async def _ainvoke(system: str, user: str, *, temperature: float = 0.4) -> str:
    if not llm_available():
        return ""
    llm = create_agent_llm("agent3", temperature=temperature, vision=False)
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    return (getattr(resp, "content", None) or "").strip()


async def humanize(text: str, style: str = "口语") -> str:
    """Apply blader/humanizer SKILL.md (official), not a local rewrite."""
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        skill = load_skill_md("humanizer", max_chars=20000)
    except FileNotFoundError as exc:
        logger.warning("%s", exc)
        return raw
    system = (
        "You are executing the Humanizer skill exactly as specified below. "
        "Follow its patterns and return rules. Do not invent facts.\n\n"
        f"--- SKILL: humanizer ---\n{skill}\n--- END SKILL ---\n\n"
        "Output only the rewritten text (no meta commentary)."
    )
    user = f"Writing context / voice: {style}\n\nText to humanize:\n\n{raw}"
    try:
        out = await _ainvoke(system, user, temperature=0.45)
        return out or raw
    except Exception as exc:
        logger.warning("humanizer skill LLM failed: %s", exc)
        return raw


async def build_html_ppt(meta: dict[str, Any], body: str, content_md: str) -> str:
    """Author deck via lewislulu/html-ppt-skill instructions + official template."""
    title = str(meta.get("title") or meta.get("topic") or "Deck")
    try:
        tpl_html, tpl_css, tpl_dir = read_html_ppt_template("tech-sharing")
        skill = load_skill_md("html-ppt", max_chars=12000)
        presenter = load_skill_ref("html-ppt", "references/presenter-mode.md", max_chars=6000)
    except FileNotFoundError as exc:
        logger.warning("html-ppt skill missing: %s", exc)
        return f"<!DOCTYPE html><html><body><h1>{title}</h1><p>html-ppt skill not installed.</p></body></html>"

    system = (
        "You are executing the html-ppt skill. Follow SKILL.md: use the provided "
        "full-deck template structure (tech-sharing), keep its CSS class names and "
        "runtime/asset link pattern, replace demo content with the user's topic.\n"
        "Prefer 6–10 slides. Include <aside class=\"notes\"> speaker notes in 口语.\n"
        "Output ONE complete HTML document only (no markdown fences if possible).\n\n"
        f"--- SKILL ---\n{skill}\n\n--- presenter-mode excerpt ---\n{presenter}\n"
        f"--- END ---\nTemplate dir: {tpl_dir.name}"
    )
    user = (
        f"Title: {title}\n\n"
        f"content.md:\n{content_md[:9000]}\n\n"
        f"--- Official template index.html (adapt, do not invent a new design system) ---\n"
        f"{tpl_html[:14000]}\n\n"
        f"--- Template style.css (keep linked as style.css or inline <style> if needed) ---\n"
        f"{tpl_css[:4000]}\n"
    )
    try:
        out = await _ainvoke(system, user, temperature=0.35)
        html = _extract_fenced(out, "html") or out
    except Exception as exc:
        logger.warning("html-ppt skill LLM failed: %s", exc)
        html = tpl_html

    if not html or "<" not in html:
        html = tpl_html

    # Always inline template CSS (blob/iframe preview cannot resolve style.css)
    if tpl_css:
        html = re.sub(
            r'<link[^>]+href=["\'][^"\']*style\.css["\'][^>]*>\s*',
            "",
            html,
            flags=re.IGNORECASE,
        )
        if "<style" not in html.lower() and "<head>" in html.lower():
            html = re.sub(
                r"(<head[^>]*>)",
                r"\1\n<style>\n" + tpl_css + "\n</style>",
                html,
                count=1,
                flags=re.IGNORECASE,
            )

    # Ensure runtime.js is present for keyboard nav
    if "runtime.js" not in html and re.search(r"</body>", html, re.I):
        html = re.sub(
            r"</body>",
            '<script src="../../../assets/runtime.js"></script>\n</body>',
            html,
            count=1,
            flags=re.IGNORECASE,
        )

    return rewrite_html_ppt_asset_hrefs(html)


async def build_podcast_script(meta: dict[str, Any], speech: str, content_md: str) -> tuple[str, str]:
    """Produce video-podcast-maker podcast.txt + a readable one_liner.md summary.

    Returns (podcast_txt, one_liner_md).
    """
    title = str(meta.get("title") or meta.get("topic") or "topic")
    try:
        skill = load_skill_md("video-podcast-maker", max_chars=10000)
        workflow = load_skill_ref(
            "video-podcast-maker", "references/workflow-script.md", max_chars=10000
        )
        narration = load_skill_ref(
            "video-podcast-maker", "references/natural-narration.md", max_chars=8000
        )
        tpl_path = skill_dir("video-podcast-maker") / "templates" / "podcast_zh.txt"
        tpl = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else ""
    except FileNotFoundError as exc:
        logger.warning("video-podcast-maker skill missing: %s", exc)
        podcast = (
            f"[SECTION:hero]\n{meta.get('hook') or title}\n\n"
            f"[SECTION:features]\n{speech[:1500]}\n\n"
            f"[SECTION:outro]\n{meta.get('cta') or '点赞关注，下期再见！'}\n"
        )
        return podcast, _podcast_to_one_liner(title, podcast)

    system = (
        "You are executing the video-podcast-maker skill for Phase 1 scripting only "
        "(Steps 3–4). Follow SKILL.md + workflow-script + natural-narration. "
        "Output ONLY a podcast.txt body with [SECTION:...] markers "
        "(hero/features/demo/summary/references/outro as appropriate). "
        "zh-CN. No markdown fences.\n\n"
        f"--- SKILL ---\n{skill}\n\n--- workflow-script ---\n{workflow}\n\n"
        f"--- natural-narration ---\n{narration}\n--- END ---"
    )
    user = (
        f"Topic: {title}\nPlatform: xiaohongshu / bilibili knowledge video\n\n"
        f"Existing speech draft (may polish into sections):\n{speech[:4000]}\n\n"
        f"content.md:\n{content_md[:8000]}\n\n"
        f"Official template podcast_zh.txt:\n{tpl[:3000]}\n"
    )
    try:
        out = await _ainvoke(system, user, temperature=0.4)
        podcast = _extract_fenced(out) or out
    except Exception as exc:
        logger.warning("video-podcast-maker script LLM failed: %s", exc)
        podcast = ""

    if "[SECTION:" not in (podcast or ""):
        podcast = (
            f"[SECTION:hero]\n{meta.get('hook') or title}\n\n"
            f"[SECTION:features]\n{(speech or content_md)[:2000]}\n\n"
            f"[SECTION:summary]\n{meta.get('summary') or ''}\n\n"
            f"[SECTION:outro]\n{meta.get('cta') or '点赞收藏加关注，评论区见！'}\n"
        )

    return podcast.strip() + "\n", _podcast_to_one_liner(title, podcast)


def _podcast_to_one_liner(title: str, podcast: str) -> str:
    """Readable table view of podcast sections (for Studio UI tab)."""
    lines = [
        f"# 视频播客脚本 — {title}",
        "",
        "> 来源 skill: video-podcast-maker（GitHub Agents365-ai）· 原生产物见 `scripts/podcast.txt`",
        "",
        "| SECTION | 口播摘要 |",
        "| --- | --- |",
    ]
    sections = re.split(r"\[SECTION:([^\]]+)\]", podcast or "")
    # split → [pre, name, body, name, body, ...]
    it = iter(sections[1:])
    for name, body in zip(it, it):
        summary = " ".join(body.strip().split())[:120]
        lines.append(f"| {name.strip()} | {summary} |")
    lines.extend(
        [
            "",
            "## 制作备注",
            "- 完整流水线见 `skills/video-podcast-maker/SKILL.md`（TTS → Remotion → MP4）",
            "- Studio beta 制作层：用 podcast/口播生成 SRT，成片仍依赖 ffmpeg/Remotion 环境",
            "",
        ]
    )
    return "\n".join(lines)


def speech_to_srt(speech: str, seconds_per_char: float = 0.18) -> str:
    """Prefer video-podcast-maker's srt helpers; fall back to estimated timings."""
    text = (speech or "").strip()
    chunks = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not chunks:
        # strip section markers for podcast.txt
        chunks = [
            ln.strip()
            for ln in re.sub(r"\[SECTION:[^\]]+\]", "\n", text).splitlines()
            if ln.strip()
        ]
    if not chunks:
        chunks = ["（空口播）"]

    # Build synthetic word boundaries and call vendor write_srt if importable
    boundaries = []
    t = 0.0
    for chunk in chunks:
        # approximate per-character timing as word units
        for ch in chunk:
            dur = max(0.05, seconds_per_char)
            boundaries.append({"text": ch, "offset": t, "duration": dur})
            t += dur
        # strong break
        boundaries.append({"text": "。", "offset": t, "duration": 0.05})
        t += 0.2

    try:
        srt_mod = _import_vpm_srt()
        if srt_mod is not None:
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False, encoding="utf-8") as f:
                tmp = Path(f.name)
            try:
                srt_mod.write_srt(boundaries, str(tmp))
                return tmp.read_text(encoding="utf-8")
            finally:
                tmp.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("vendor srt unavailable: %s", exc)

    # Minimal SRT without rewriting vendor logic in detail
    blocks = []
    t = 0.0

    def fmt(sec: float) -> str:
        ms = int(sec * 1000)
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    for i, chunk in enumerate(chunks, 1):
        dur = max(1.2, min(8.0, len(chunk) * seconds_per_char))
        start, end = t, t + dur
        blocks.append(f"{i}\n{fmt(start)} --> {fmt(end)}\n{chunk}\n")
        t = end + 0.15
    return "\n".join(blocks)


def _import_vpm_srt():
    """Load skills/video-podcast-maker/scripts/tts/srt.py by path (avoid PyPI name clash)."""
    import importlib.util

    path = skill_dir("video-podcast-maker") / "scripts" / "tts" / "srt.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("vpm_tts_srt", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
