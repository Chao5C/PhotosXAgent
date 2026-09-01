"""Load official Agent Skills from skills/ (vendored from GitHub — do not rewrite)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

# PhotosXAgent repo root (photosx/studio → ../..)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / "skills"

KNOWN_SKILLS = {
    "humanizer": "humanizer",
    "html-ppt": "html-ppt",
    "video-podcast-maker": "video-podcast-maker",
}


def skills_root() -> Path:
    return _SKILLS_ROOT


def skill_dir(name: str) -> Path:
    key = KNOWN_SKILLS.get(name, name)
    path = _SKILLS_ROOT / key
    if not path.is_dir():
        raise FileNotFoundError(f"Skill not found: {name} (expected {path})")
    origin = path / "ORIGIN.txt"
    if origin.exists() and "do_not_rewrite=true" not in origin.read_text(encoding="utf-8", errors="ignore"):
        pass  # soft check
    return path


def _strip_yaml_frontmatter(text: str) -> str:
    text = text or ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


@lru_cache(maxsize=32)
def load_skill_md(name: str, *, max_chars: int = 24000) -> str:
    """Return SKILL.md body (frontmatter stripped) for prompt injection."""
    path = skill_dir(name) / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing SKILL.md for {name}")
    body = _strip_yaml_frontmatter(path.read_text(encoding="utf-8"))
    if len(body) > max_chars:
        body = body[:max_chars] + "\n\n…(truncated for context window)…"
    return body


@lru_cache(maxsize=64)
def load_skill_ref(name: str, rel: str, *, max_chars: int = 16000) -> str:
    path = skill_dir(name) / rel
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n…(truncated)…"
    return text


def skill_asset_url_prefix(name: str) -> str:
    """Public URL prefix for skill static assets (mounted by studio router)."""
    return f"/api/studio/skill-assets/{KNOWN_SKILLS.get(name, name)}"


def rewrite_html_ppt_asset_hrefs(html: str, *, skill: str = "html-ppt") -> str:
    """Rewrite template-relative asset paths to studio skill-asset URLs."""
    prefix = skill_asset_url_prefix(skill)
    # ../../../assets/... or ../../assets/... or ../assets/...
    html = re.sub(
        r'(href|src)=(["\'])(?:\.\./)+assets/',
        rf'\1=\2{prefix}/assets/',
        html,
    )
    html = re.sub(
        r'(href|src)=(["\'])assets/',
        rf'\1=\2{prefix}/assets/',
        html,
    )
    # runtime.js often next to assets
    html = re.sub(
        r'(src)=(["\'])(?:\.\./)+assets/runtime\.js',
        rf'\1=\2{prefix}/assets/runtime.js',
        html,
    )
    return html


def read_html_ppt_template(template: str = "tech-sharing") -> tuple[str, str, Path]:
    """Return (index_html, style_css, template_dir) from official html-ppt skill."""
    tpl = skill_dir("html-ppt") / "templates" / "full-decks" / template
    index = tpl / "index.html"
    style = tpl / "style.css"
    if not index.exists():
        raise FileNotFoundError(f"html-ppt template missing: {tpl}")
    return (
        index.read_text(encoding="utf-8"),
        style.read_text(encoding="utf-8") if style.exists() else "",
        tpl,
    )


def resolve_skill_file(skill: str, rel: str) -> Optional[Path]:
    base = skill_dir(skill).resolve()
    path = (base / rel).resolve()
    if base not in path.parents and path != base:
        return None
    return path if path.exists() else None
