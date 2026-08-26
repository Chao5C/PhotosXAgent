from typing import Optional, Tuple

import httpx


async def reverse_geocode(lat: float, lng: float) -> dict:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 14, "addressdetails": 1}
    headers = {"User-Agent": "PhotosXAgent/0.1"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        address = data.get("address") or {}
        city = address.get("city") or address.get("town") or address.get("county") or address.get("state")
        return {
            "place_name": data.get("name") or data.get("display_name"),
            "display_name": data.get("display_name"),
            "city": city,
            "country": address.get("country"),
            "country_code": address.get("country_code"),
        }
    except Exception:
        return {"place_name": None, "display_name": None, "city": None, "country": None}


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


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    from math import radians, sin, cos, sqrt, atan2

    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))
