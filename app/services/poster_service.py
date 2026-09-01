from __future__ import annotations

import base64
import logging
import textwrap
from pathlib import Path
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.utils.serialize import serialize, utcnow

logger = logging.getLogger(__name__)

POSTER_WIDTH = 1080
POSTER_HEIGHT = 1520


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            trial = current + ch
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def render_poster_png(guide: dict[str, Any], out_path: Path) -> bool:
    img = Image.new("RGB", (POSTER_WIDTH, POSTER_HEIGHT), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(52)
    body_font = _load_font(28)
    small_font = _load_font(24)

    draw.rectangle((0, 0, POSTER_WIDTH, 260), fill=(29, 78, 216))
    draw.text((60, 50), (guide.get("place") or "Travel Guide"), fill=(125, 211, 252), font=small_font)
    title = (guide.get("title") or "出行攻略")[:20]
    draw.text((60, 95), title, fill=(248, 250, 252), font=title_font)
    weather = (guide.get("weather_brief") or "")[:80]
    if weather:
        draw.text((60, 190), weather, fill=(203, 213, 225), font=small_font)

    y = 300
    body_lines = _wrap_text(draw, guide.get("body") or "", body_font, POSTER_WIDTH - 120)
    for line in body_lines[:14]:
        draw.text((60, y), line, fill=(226, 232, 240), font=body_font)
        y += 42

    y += 10
    draw.text((60, y), "推荐关注", fill=(56, 189, 248), font=body_font)
    y += 44
    for item in (guide.get("highlights") or [])[:4]:
        draw.text((80, y), f"• {item}", fill=(203, 213, 225), font=small_font)
        y += 36

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return True


class PosterService:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.base_dir = settings.upload_path / user_id / "posters"

    async def create_from_guide(self, db: AsyncIOMotorDatabase, guide: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        doc = {
            "user_id": self.user_id,
            "title": (guide.get("title") or "出行攻略").strip(),
            "place": (guide.get("place") or "").strip(),
            "body_preview": ((guide.get("body") or "")[:180]).strip(),
            "highlights": guide.get("highlights") or [],
            "weather_brief": guide.get("weather_brief") or "",
            "created_at": now,
        }
        inserted = await db.posters.insert_one(doc)
        poster_id = str(inserted.inserted_id)
        png_path = self.base_dir / f"{poster_id}.png"
        render_poster_png(guide, png_path)
        raw = png_path.read_bytes()
        image_data_url = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
        await db.posters.update_one({"_id": inserted.inserted_id}, {"$set": {"filename": png_path.name}})
        payload = {
            "id": poster_id,
            "title": doc["title"],
            "place": doc["place"],
            "image_url": f"/api/posters/{poster_id}/file",
            "image_data_url": image_data_url,
            "created_at": now.isoformat(),
        }
        return payload

    async def list_posters(self, db: AsyncIOMotorDatabase, limit: int = 60) -> list[dict]:
        cursor = db.posters.find({"user_id": self.user_id}).sort("created_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            item = serialize(doc) or {}
            pid = item.get("id")
            items.append(
                {
                    "id": pid,
                    "title": item.get("title") or "出行攻略",
                    "place": item.get("place") or "",
                    "body_preview": item.get("body_preview") or "",
                    "highlights": item.get("highlights") or [],
                    "weather_brief": item.get("weather_brief") or "",
                    "image_url": f"/api/posters/{pid}/file" if pid else "",
                    "created_at": item.get("created_at"),
                }
            )
        return items

    async def get_file_path(self, db: AsyncIOMotorDatabase, poster_id: str) -> Path | None:
        try:
            oid = ObjectId(poster_id)
        except Exception:
            return None
        doc = await db.posters.find_one({"_id": oid, "user_id": self.user_id})
        if not doc:
            return None
        path = self.base_dir / f"{poster_id}.png"
        return path if path.exists() else None

    async def delete_poster(self, db: AsyncIOMotorDatabase, poster_id: str) -> bool:
        try:
            oid = ObjectId(poster_id)
        except Exception:
            return False
        doc = await db.posters.find_one({"_id": oid, "user_id": self.user_id})
        if not doc:
            return False
        path = self.base_dir / f"{poster_id}.png"
        if path.exists():
            path.unlink()
        await db.posters.delete_one({"_id": oid})
        return True
