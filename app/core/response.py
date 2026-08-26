from datetime import datetime, timezone
from typing import Any, Dict, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": now_iso(),
    }


def fail(message: str = "error", code: int = 500, data: Any = None) -> Dict[str, Any]:
    return {
        "success": False,
        "data": data,
        "message": message,
        "code": code,
        "timestamp": now_iso(),
    }
