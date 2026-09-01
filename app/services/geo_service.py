from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _short_display_name(display_name: str) -> str:
    text = _clean_text(display_name)
    if not text:
        return ""
    return text.split(",")[0].strip()


def _china_city_from_address(address: dict) -> Optional[str]:
    for key in (
        "city",
        "town",
        "district",
        "county",
        "suburb",
        "village",
        "municipality",
        "state_district",
        "borough",
        "state",
    ):
        val = _clean_text(address.get(key))
        if val:
            return val
    return None


def _amap_key() -> str:
    return (getattr(settings, "AMAP_WEB_KEY", None) or "").strip()


async def _reverse_geocode_gaode(lat: float, lng: float) -> dict:
    key = _amap_key()
    if not key:
        return {}
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "key": key,
        "location": f"{lng},{lat}",
        "extensions": "all",
        "radius": 1000,
        "output": "JSON",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if str(data.get("status")) != "1":
            logger.warning("Gaode regeo failed: %s", data.get("info") or data)
            return {}
        regeo = data.get("regeocode") or {}
        comp = regeo.get("addressComponent") or {}
        province = _clean_text(comp.get("province"))
        city = _clean_text(comp.get("city")) or province
        district = _clean_text(comp.get("district"))
        township = _clean_text(comp.get("township"))
        street = _clean_text(comp.get("street"))
        street_no = _clean_text(comp.get("streetNumber"))
        formatted = _clean_text(regeo.get("formatted_address"))

        street_line = f"{street}{street_no}" if street else ""
        short_parts = [p for p in (district, township, street_line) if p]
        place_name = " ".join(short_parts) if short_parts else (district or city or formatted)

        pois = regeo.get("pois") or []
        poi_name = _clean_text((pois[0] or {}).get("name")) if pois else ""

        return {
            "place_name": place_name or formatted or None,
            "display_name": formatted or place_name or None,
            "city": city or None,
            "district": district or None,
            "province": province or None,
            "township": township or None,
            "street": street_line or None,
            "poi_name": poi_name or None,
            "country": "中国",
            "country_code": "cn",
            "source": "amap",
        }
    except Exception as exc:
        logger.warning("Gaode reverse geocode failed for %.5f,%.5f: %s", lat, lng, exc)
        return {}


async def reverse_geocode(lat: float, lng: float) -> dict:
    """Resolve coordinates to a place name. Prefer Gaode when AMAP_WEB_KEY is configured."""
    base = {"lat": lat, "lng": lng}

    gaode = await _reverse_geocode_gaode(lat, lng)
    if gaode.get("place_name") or gaode.get("city") or gaode.get("display_name"):
        return {**base, **gaode}

    if _amap_key() and 18 <= lat <= 54 and 73 <= lng <= 135:
        logger.warning("Gaode returned empty for %.5f,%.5f — check AMAP_WEB_KEY permissions", lat, lng)

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 14, "addressdetails": 1, "accept-language": "zh-CN,en"}
    headers = {"User-Agent": "PhotosXAgent/0.1"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        address = data.get("address") or {}
        city = _china_city_from_address(address)
        place_name = _clean_text(data.get("name")) or _short_display_name(data.get("display_name") or "")
        return {
            **base,
            "place_name": place_name or city,
            "display_name": data.get("display_name"),
            "city": city,
            "district": _clean_text(address.get("district") or address.get("suburb")),
            "country": address.get("country"),
            "country_code": address.get("country_code"),
            "source": "nominatim",
        }
    except Exception as exc:
        logger.warning("Nominatim reverse geocode failed for %.5f,%.5f: %s", lat, lng, exc)
        return {**base, "place_name": None, "display_name": None, "city": None, "country": None, "source": "none"}


def resolve_photo_place(geo: dict | None, metadata: dict | None = None) -> Optional[str]:
    """Display place from GPS reverse-geocode only (never LLM landmark)."""
    geo = geo or {}
    metadata = metadata or {}

    for key in ("place_name", "city", "district", "township", "street", "display_name"):
        val = _clean_text(geo.get(key))
        if not val:
            continue
        if key == "display_name":
            val = _short_display_name(val)
        return val

    lat, lng = metadata.get("lat"), metadata.get("lng")
    if lat is not None and lng is not None:
        return f"{float(lat):.4f}, {float(lng):.4f}"
    return None


def enrich_geo(metadata: dict, geo: dict | None) -> dict:
    """Attach coordinates and normalize reverse-geocode fields. Does not use LLM output."""
    geo = dict(geo or {})
    lat, lng = metadata.get("lat"), metadata.get("lng")
    if lat is not None and lng is not None:
        geo["lat"] = float(lat)
        geo["lng"] = float(lng)

    if not _clean_text(geo.get("place_name")) and _clean_text(geo.get("display_name")):
        geo["place_name"] = _short_display_name(geo["display_name"])

    if not _clean_text(geo.get("city")) and _clean_text(geo.get("district")):
        geo["city"] = geo["district"]

    return geo


async def geocode_photo_from_metadata(metadata: dict) -> dict:
    lat, lng = metadata.get("lat"), metadata.get("lng")
    if lat is None or lng is None:
        return {}
    geo = await reverse_geocode(float(lat), float(lng))
    return enrich_geo(metadata, geo)


def _normalize_place_query(place: str) -> str:
    text = _clean_text(place)
    if not text:
        return ""
    if text.endswith(("市", "省", "区", "县", "州", "国", "自治区", "特别行政区")):
        return text
    if len(text) <= 4 and all("\u4e00" <= ch <= "\u9fff" for ch in text):
        return f"{text}市"
    return text


async def _forward_geocode_gaode(place: str) -> dict:
    key = _amap_key()
    if not key:
        return {}
    address = _normalize_place_query(place)
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"key": key, "address": address, "output": "JSON"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if str(data.get("status")) != "1":
            logger.warning("Gaode geocode failed for %s: %s", address, data.get("info") or data)
            return {}
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return {}
        item = geocodes[0] or {}
        location = _clean_text(item.get("location"))
        if not location or "," not in location:
            return {}
        lng_s, lat_s = location.split(",", 1)
        city = _clean_text(item.get("city")) or _clean_text(item.get("province"))
        district = _clean_text(item.get("district"))
        formatted = _clean_text(item.get("formatted_address"))
        return {
            "lat": float(lat_s),
            "lng": float(lng_s),
            "place_name": district or city or formatted or place,
            "display_name": formatted or city or place,
            "city": city or place,
            "district": district or None,
            "province": _clean_text(item.get("province")) or None,
            "country": "中国",
            "country_code": "cn",
            "source": "amap",
        }
    except Exception as exc:
        logger.warning("Gaode forward geocode failed for %s: %s", place, exc)
        return {}


async def geocode_place_name(place: str) -> dict:
    """Resolve a place name (e.g. 上海) to coordinates and normalized labels."""
    text = _clean_text(place)
    if not text:
        return {}

    gaode = await _forward_geocode_gaode(text)
    if gaode.get("lat") is not None and gaode.get("lng") is not None:
        return gaode

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": text, "format": "jsonv2", "limit": 1, "accept-language": "zh-CN,en"}
    headers = {"User-Agent": "PhotosXAgent/0.1"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            items = resp.json()
        if not items:
            return {"place_name": text, "display_name": text, "city": text, "source": "none"}
        item = items[0] or {}
        lat = float(item.get("lat"))
        lng = float(item.get("lon"))
        display = _clean_text(item.get("display_name"))
        address = item.get("address") or {}
        city = _china_city_from_address(address) or text
        return {
            "lat": lat,
            "lng": lng,
            "place_name": _short_display_name(display) or city,
            "display_name": display or city,
            "city": city,
            "district": _clean_text(address.get("district") or address.get("suburb")),
            "country": address.get("country"),
            "country_code": address.get("country_code"),
            "source": "nominatim",
        }
    except Exception as exc:
        logger.warning("Nominatim forward geocode failed for %s: %s", text, exc)
        return {"place_name": text, "display_name": text, "city": text, "source": "none"}


async def fetch_weather(lat: float, lng: float) -> Optional[dict]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current_weather": True,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone": "auto",
        "forecast_days": 3,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import radians, sin, cos, sqrt, atan2

    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))
