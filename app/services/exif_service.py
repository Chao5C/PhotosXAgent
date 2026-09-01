from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ExifTags, ImageFile
from PIL.ExifTags import GPSTAGS

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = logging.getLogger(__name__)


def _ratio_to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return float(value.numerator) / float(value.denominator or 1)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return float(value[0]) / float(value[1] or 1)
        return 0.0


def _dms_to_decimal(dms, ref: Optional[str]) -> Optional[float]:
    if not dms or len(dms) < 3:
        return None
    degrees = _ratio_to_float(dms[0]) + _ratio_to_float(dms[1]) / 60 + _ratio_to_float(dms[2]) / 3600
    if ref in ("S", "W"):
        degrees = -degrees
    return degrees


def extract_exif(file_path: Path) -> dict:
    result = {
        "taken_at": None,
        "lat": None,
        "lng": None,
        "camera": None,
        "orientation": None,
        "raw": {},
    }
    try:
        with Image.open(file_path) as image:
            exif = image.getexif()
            if not exif:
                return result

            tagged = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            camera_make = tagged.get("Make")
            camera_model = tagged.get("Model")
            if camera_make or camera_model:
                result["camera"] = " ".join(str(part).strip() for part in [camera_make, camera_model] if part)
            serial = (
                tagged.get("BodySerialNumber")
                or tagged.get("SerialNumber")
                or tagged.get("CameraSerialNumber")
                or tagged.get("InternalSerialNumber")
            )
            if serial:
                result["device_id"] = str(serial).strip()
            elif result.get("camera"):
                result["device_id"] = result["camera"]

            dt = tagged.get("DateTimeOriginal") or tagged.get("DateTime")
            if dt:
                try:
                    result["taken_at"] = datetime.strptime(str(dt), "%Y:%m:%d %H:%M:%S").isoformat()
                except ValueError:
                    result["taken_at"] = str(dt)

            gps_ifd = None
            try:
                gps_ifd = exif.get_ifd(0x8825)
            except Exception:
                gps_ifd = None

            if gps_ifd:
                gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
                lat = _dms_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
                lng = _dms_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
                result["lat"] = lat
                result["lng"] = lng

            result["orientation"] = tagged.get("Orientation")
            result["raw"] = {
                "Make": str(camera_make) if camera_make else None,
                "Model": str(camera_model) if camera_model else None,
                "DateTime": str(dt) if dt else None,
            }
    except Exception as exc:
        logger.warning("EXIF extract failed for %s: %s", file_path, exc)
    return result


def _open_rgb_image(file_path: Path | str, max_side: int | None = None) -> Image.Image:
    path = Path(file_path)
    last_error: Exception | None = None
    candidates = [path]
    thumb = path.parent / f"{path.stem}_thumb.jpg"
    if thumb.exists() and thumb.resolve() != path.resolve():
        candidates.append(thumb)

    for candidate in candidates:
        try:
            with Image.open(candidate) as image:
                image.load()
                rgb = image.convert("RGB")
                if max_side:
                    rgb.thumbnail((max_side, max_side))
                return rgb.copy()
        except Exception as exc:
            last_error = exc
            logger.warning("open image failed for %s: %s", candidate, exc)
    raise RuntimeError(f"无法读取图片: {last_error}") from last_error


def make_thumbnail(file_path: Path | str, dest: Path | str, size: int = 480) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = _open_rgb_image(file_path, max_side=size)
    try:
        image.save(dest, "JPEG", quality=82)
    finally:
        image.close()


def image_to_jpeg_bytes(file_path: Path | str, max_side: int = 1280) -> bytes:
    image = _open_rgb_image(file_path, max_side=max_side)
    try:
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=80)
        return buffer.getvalue()
    finally:
        image.close()
