from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from photosx.studio import (
    DERIVED_SCRIPTS,
    artifact_stale,
    content_fingerprint,
    ensure_topic_dirs,
    file_sha1,
    load_manifest,
    mark_artifact,
    parse_content_md,
    render_content_md,
    save_manifest,
    slugify,
    utcnow_iso,
)
from photosx.studio.research import build_content_body, synthesize_research, web_search
from photosx.studio.skill_runtime import build_html_ppt, build_podcast_script, speech_to_srt
from photosx.agents.studio_agent import derive_all

logger = logging.getLogger(__name__)


class StudioService:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.root = settings.topics_path / user_id
        self.root.mkdir(parents=True, exist_ok=True)

    def _topic_dir(self, topic_id: str) -> Path:
        path = (self.root / topic_id).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError("非法选题路径")
        return path

    def list_topics(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_dir():
                continue
            content = path / "content.md"
            meta, _ = parse_content_md(content.read_text(encoding="utf-8")) if content.exists() else ({}, "")
            manifest = load_manifest(path)
            items.append(
                {
                    "id": path.name,
                    "title": meta.get("title") or path.name,
                    "status": meta.get("status") or "draft",
                    "updated_at": meta.get("updated_at") or manifest.get("updated_at"),
                    "artifacts": list((manifest.get("artifacts") or {}).keys()),
                }
            )
        return items

    def create_topic(self, title: str, seed: str = "") -> dict[str, Any]:
        day = datetime.now().strftime("%Y-%m-%d")
        topic_id = f"{day}-{slugify(title)}"
        base = topic_id
        n = 1
        while (self.root / topic_id).exists():
            n += 1
            topic_id = f"{base}-{n}"
        topic_dir = self.root / topic_id
        ensure_topic_dirs(topic_dir)
        meta = {
            "title": title,
            "topic": title,
            "status": "created",
            "created_at": utcnow_iso(),
            "updated_at": utcnow_iso(),
            "voice_id": settings.STUDIO_VOICE_ID,
            "sources": [],
            "claims": [],
            "hook": "",
            "summary": seed[:200] if seed else "",
            "cta": "",
        }
        body = f"# {title}\n\n## 草稿\n\n{seed or '（调研后由系统填充）'}\n"
        (topic_dir / "content.md").write_text(render_content_md(meta, body), encoding="utf-8")
        save_manifest(topic_dir, {"version": 1, "artifacts": {}})
        return self.get_topic(topic_id)

    def get_topic(self, topic_id: str) -> dict[str, Any]:
        topic_dir = self._topic_dir(topic_id)
        if not topic_dir.exists():
            raise FileNotFoundError("选题不存在")
        content_path = topic_dir / "content.md"
        raw = content_path.read_text(encoding="utf-8") if content_path.exists() else ""
        meta, body = parse_content_md(raw)
        manifest = load_manifest(topic_dir)
        files = {
            "content.md": content_path.exists(),
            **{name: (topic_dir / rel).exists() for name, rel in DERIVED_SCRIPTS.items()},
            "subtitle": (topic_dir / "assets/subtitle/speech.srt").exists(),
            "output_readme": (topic_dir / "output/STATUS.md").exists(),
        }
        return {
            "id": topic_id,
            "path": str(topic_dir),
            "meta": meta,
            "body": body,
            "content_md": raw,
            "manifest": manifest,
            "files": files,
            "content_hash": content_fingerprint(topic_dir),
        }

    def update_content(self, topic_id: str, content_md: str) -> dict[str, Any]:
        topic_dir = self._topic_dir(topic_id)
        ensure_topic_dirs(topic_dir)
        meta, body = parse_content_md(content_md)
        meta["updated_at"] = utcnow_iso()
        if "title" not in meta:
            meta["title"] = topic_id
        text = render_content_md(meta, body)
        (topic_dir / "content.md").write_text(text, encoding="utf-8")
        # 标记派生产物过期
        manifest = load_manifest(topic_dir)
        for name, art in list((manifest.get("artifacts") or {}).items()):
            if name == "research":
                continue
            art["status"] = "stale"
        save_manifest(topic_dir, manifest)
        return self.get_topic(topic_id)

    def delete_topic(self, topic_id: str) -> None:
        topic_dir = self._topic_dir(topic_id)
        if topic_dir.exists():
            shutil.rmtree(topic_dir)

    async def research(self, topic_id: str, query: str | None = None) -> dict[str, Any]:
        topic = self.get_topic(topic_id)
        topic_dir = self._topic_dir(topic_id)
        title = topic["meta"].get("title") or topic_id
        q = (query or title).strip()
        sources = await web_search(q, limit=6)
        research = await synthesize_research(title, sources)
        snapshot = {
            "query": q,
            "fetched_at": utcnow_iso(),
            "sources": sources,
            "research": research,
        }
        (topic_dir / "research" / "snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (topic_dir / "research" / "sources.md").write_text(
            "\n".join(
                f"- [{s.get('title')}]({s.get('url')})\n  {s.get('snippet')}" for s in sources
            )
            or "- （无检索结果）\n",
            encoding="utf-8",
        )
        meta = dict(topic["meta"])
        meta.update(
            {
                "status": "researched",
                "updated_at": utcnow_iso(),
                "hook": research.get("hook") or meta.get("hook"),
                "summary": research.get("summary") or meta.get("summary"),
                "claims": research.get("claims") or [],
                "cta": research.get("cta") or meta.get("cta"),
                "hot_score": research.get("hot_score"),
                "risks": research.get("risks") or [],
                "sources": [
                    {"title": s.get("title"), "url": s.get("url"), "snippet": s.get("snippet")}
                    for s in sources
                ],
            }
        )
        body = build_content_body(title, research, sources)
        (topic_dir / "content.md").write_text(render_content_md(meta, body), encoding="utf-8")
        ch = content_fingerprint(topic_dir)
        manifest = load_manifest(topic_dir)
        mark_artifact(
            manifest,
            "research",
            path="research/snapshot.json",
            content_hash=ch,
            file_hash=file_sha1(topic_dir / "research/snapshot.json"),
            status="ready",
        )
        for name in list((manifest.get("artifacts") or {}).keys()):
            if name != "research":
                manifest["artifacts"][name]["status"] = "stale"
        save_manifest(topic_dir, manifest)
        return self.get_topic(topic_id)

    async def derive(self, topic_id: str, force: bool = False) -> dict[str, Any]:
        topic = self.get_topic(topic_id)
        topic_dir = self._topic_dir(topic_id)
        ch = topic["content_hash"]
        manifest = load_manifest(topic_dir)
        need = force or any(
            artifact_stale(manifest, name, ch)
            for name in ("speech", "moments", "xhs", "wechat", "html_ppt", "one_liner", "podcast")
        )
        if not need and all((topic_dir / rel).exists() for rel in DERIVED_SCRIPTS.values()):
            return self.get_topic(topic_id)

        scripts = await derive_all(topic["content_md"], topic["meta"])
        mapping = {
            "speech": scripts["speech"],
            "moments": scripts["moments"],
            "xhs": scripts["xhs"],
            "wechat": scripts["wechat"],
        }
        for name, text in mapping.items():
            rel = DERIVED_SCRIPTS[name]
            path = topic_dir / rel
            path.write_text(text.strip() + "\n", encoding="utf-8")
            mark_artifact(manifest, name, path=rel, content_hash=ch, file_hash=file_sha1(path), status="ready")

        ppt = await build_html_ppt(topic["meta"], topic["body"], topic["content_md"])
        ppt_path = topic_dir / DERIVED_SCRIPTS["html_ppt"]
        ppt_path.write_text(ppt, encoding="utf-8")
        mark_artifact(manifest, "html_ppt", path=DERIVED_SCRIPTS["html_ppt"], content_hash=ch, file_hash=file_sha1(ppt_path), status="ready")

        podcast, one = await build_podcast_script(topic["meta"], scripts["speech"], topic["content_md"])
        podcast_path = topic_dir / DERIVED_SCRIPTS["podcast"]
        podcast_path.write_text(podcast, encoding="utf-8")
        mark_artifact(
            manifest,
            "podcast",
            path=DERIVED_SCRIPTS["podcast"],
            content_hash=ch,
            file_hash=file_sha1(podcast_path),
            deps={"speech": file_sha1(topic_dir / DERIVED_SCRIPTS["speech"])},
            status="ready",
        )
        one_path = topic_dir / DERIVED_SCRIPTS["one_liner"]
        one_path.write_text(one, encoding="utf-8")
        mark_artifact(
            manifest,
            "one_liner",
            path=DERIVED_SCRIPTS["one_liner"],
            content_hash=ch,
            file_hash=file_sha1(one_path),
            deps={"podcast": file_sha1(podcast_path)},
            status="ready",
        )

        meta = dict(topic["meta"])
        meta["status"] = "derived"
        meta["updated_at"] = utcnow_iso()
        (topic_dir / "content.md").write_text(render_content_md(meta, topic["body"]), encoding="utf-8")
        # content hash may change slightly due to meta status — refresh fingerprint bindings
        ch2 = content_fingerprint(topic_dir)
        for name in ("speech", "moments", "xhs", "wechat", "html_ppt", "one_liner", "podcast"):
            if name in (manifest.get("artifacts") or {}):
                manifest["artifacts"][name]["content_hash"] = ch2
        save_manifest(topic_dir, manifest)
        return self.get_topic(topic_id)

    async def produce(self, topic_id: str, force: bool = False) -> dict[str, Any]:
        """制作层：字幕对齐 + TTS/成片占位。真实 ffmpeg/TTS 可后续接入。"""
        topic = await self.derive(topic_id, force=False)
        topic_dir = self._topic_dir(topic_id)
        ch = content_fingerprint(topic_dir)
        manifest = load_manifest(topic_dir)
        speech_path = topic_dir / DERIVED_SCRIPTS["speech"]
        speech = speech_path.read_text(encoding="utf-8") if speech_path.exists() else ""
        podcast_path = topic_dir / DERIVED_SCRIPTS["podcast"]
        srt_source = podcast_path.read_text(encoding="utf-8") if podcast_path.exists() else speech

        srt = speech_to_srt(srt_source)
        srt_path = topic_dir / "assets/subtitle/speech.srt"
        srt_path.write_text(srt, encoding="utf-8")
        mark_artifact(
            manifest,
            "subtitle",
            path="assets/subtitle/speech.srt",
            content_hash=ch,
            file_hash=file_sha1(srt_path),
            deps={"speech": file_sha1(speech_path)},
            status="ready",
        )

        # 画面：复制 HTML-PPT 到 visual
        deck = topic_dir / DERIVED_SCRIPTS["html_ppt"]
        visual = topic_dir / "assets/visual/deck.html"
        if deck.exists():
            visual.write_text(deck.read_text(encoding="utf-8"), encoding="utf-8")
        mark_artifact(
            manifest,
            "visual",
            path="assets/visual/deck.html",
            content_hash=ch,
            file_hash=file_sha1(visual) if visual.exists() else "",
            deps={"html_ppt": file_sha1(deck)},
            status="ready" if visual.exists() else "missing",
        )

        voice_path = topic_dir / "assets/voice/speech.txt"
        voice_path.write_text(
            "\n".join(
                [
                    f"voice_id={settings.STUDIO_VOICE_ID}",
                    f"tts_enabled={settings.STUDIO_TTS_ENABLED}",
                    "",
                    speech,
                ]
            ),
            encoding="utf-8",
        )
        tts_status = "stub"
        if settings.STUDIO_TTS_ENABLED:
            tts_status = await self._try_tts(speech, topic_dir / "assets/voice/speech.wav")
        mark_artifact(
            manifest,
            "voice",
            path="assets/voice/speech.wav" if tts_status == "ready" else "assets/voice/speech.txt",
            content_hash=ch,
            file_hash=file_sha1(topic_dir / "assets/voice/speech.wav")
            if tts_status == "ready"
            else file_sha1(voice_path),
            deps={"speech": file_sha1(speech_path)},
            status=tts_status,
        )

        bgm_note = topic_dir / "assets/bgm/README.md"
        if not bgm_note.exists():
            bgm_note.write_text("# 配乐\n放入 mp3/wav 后，成片阶段会自动垫乐（beta 未自动合成）。\n", encoding="utf-8")

        status_md = topic_dir / "output/STATUS.md"
        status_md.write_text(
            "\n".join(
                [
                    f"# 成片状态 — {topic['meta'].get('title')}",
                    "",
                    f"- 更新时间：{utcnow_iso()}",
                    f"- TTS：{tts_status}（`STUDIO_TTS_ENABLED={settings.STUDIO_TTS_ENABLED}`）",
                    "- 字幕：assets/subtitle/speech.srt",
                    "- 画面：assets/visual/deck.html",
                    "- 视频合成：按 skills/video-podcast-maker（Remotion/ffmpeg）；beta 多为占位",
                    "",
                    "## 手动成片清单",
                    "1. 确认 scripts/podcast.txt（video-podcast-maker）与 speech.md",
                    "2. 在 skill 环境跑 TTS / Remotion，或用 TTS 生成 assets/voice/speech.wav",
                    "3. 导入 SRT + 画面静帧 + BGM",
                    "4. 导出到 output/final.mp4",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        mark_artifact(
            manifest,
            "output",
            path="output/STATUS.md",
            content_hash=ch,
            file_hash=file_sha1(status_md),
            status="pending_render",
        )

        meta = dict(topic["meta"])
        meta["status"] = "produced"
        meta["updated_at"] = utcnow_iso()
        (topic_dir / "content.md").write_text(render_content_md(meta, topic["body"]), encoding="utf-8")
        save_manifest(topic_dir, manifest)
        return self.get_topic(topic_id)

    async def _try_tts(self, speech: str, wav_path: Path) -> str:
        try:
            import edge_tts  # type: ignore
        except Exception:
            return "stub_no_edge_tts"
        try:
            communicate = edge_tts.Communicate(speech[:3000], "zh-CN-XiaoxiaoNeural")
            await communicate.save(str(wav_path.with_suffix(".mp3")))
            return "ready"
        except Exception as exc:
            logger.warning("edge_tts failed: %s", exc)
            return "tts_failed"

    def read_file(self, topic_id: str, rel: str) -> dict[str, Any]:
        topic_dir = self._topic_dir(topic_id)
        path = (topic_dir / rel).resolve()
        if topic_dir.resolve() not in path.parents and path != topic_dir.resolve():
            raise ValueError("非法路径")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("文件不存在")
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"path": rel, "content": text}

    async def run_pipeline(self, topic_id: str, stages: Optional[list[str]] = None) -> dict[str, Any]:
        stages = stages or ["research", "derive", "produce"]
        result = self.get_topic(topic_id)
        if "research" in stages:
            result = await self.research(topic_id)
        if "derive" in stages:
            result = await self.derive(topic_id)
        if "produce" in stages:
            result = await self.produce(topic_id)
        return result
