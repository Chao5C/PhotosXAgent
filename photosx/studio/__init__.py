from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

TOPIC_SUBDIRS = [
    "research",
    "scripts",
    "assets/voice",
    "assets/subtitle",
    "assets/visual",
    "assets/bgm",
    "output",
]

DERIVED_SCRIPTS = {
    "speech": "scripts/speech.md",
    "moments": "scripts/moments.md",
    "xhs": "scripts/xhs.md",
    "wechat": "scripts/wechat.md",
    "one_liner": "scripts/one_liner.md",
    "podcast": "scripts/podcast.txt",
    "html_ppt": "scripts/deck.html",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:80] or "untitled"


def file_sha1(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha1(path.read_bytes()).hexdigest()


def parse_content_md(text: str) -> tuple[dict[str, Any], str]:
    text = text or ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
            return (meta if isinstance(meta, dict) else {}), body
    return {}, text


def render_content_md(meta: dict[str, Any], body: str) -> str:
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{body.rstrip()}\n"


def load_manifest(topic_dir: Path) -> dict[str, Any]:
    path = topic_dir / ".manifest.json"
    if not path.exists():
        return {"version": 1, "artifacts": {}, "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "artifacts": {}, "updated_at": None}


def save_manifest(topic_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utcnow_iso()
    (topic_dir / ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def content_fingerprint(topic_dir: Path) -> str:
    return file_sha1(topic_dir / "content.md")


def ensure_topic_dirs(topic_dir: Path) -> None:
    topic_dir.mkdir(parents=True, exist_ok=True)
    for rel in TOPIC_SUBDIRS:
        (topic_dir / rel).mkdir(parents=True, exist_ok=True)


def artifact_stale(manifest: dict[str, Any], name: str, content_hash: str, deps: Optional[list[str]] = None) -> bool:
    art = (manifest.get("artifacts") or {}).get(name) or {}
    if art.get("content_hash") != content_hash:
        return True
    for dep in deps or []:
        if art.get("deps", {}).get(dep) != (manifest.get("artifacts") or {}).get(dep, {}).get("hash"):
            return True
    return False


def mark_artifact(
    manifest: dict[str, Any],
    name: str,
    *,
    path: str,
    content_hash: str,
    file_hash: str,
    deps: Optional[dict[str, str]] = None,
    status: str = "ready",
) -> None:
    artifacts = manifest.setdefault("artifacts", {})
    artifacts[name] = {
        "path": path,
        "content_hash": content_hash,
        "hash": file_hash,
        "deps": deps or {},
        "status": status,
        "updated_at": utcnow_iso(),
    }
