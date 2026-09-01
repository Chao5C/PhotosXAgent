from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId

_INVALID_OID_STRINGS = frozenset({"undefined", "null", "none", ""})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_valid_object_id(value: str | None) -> bool:
    try:
        parse_object_id(value)
        return True
    except ValueError:
        return False


def parse_object_id(value: str | None, *, field: str = "id") -> ObjectId:
    text = str(value or "").strip()
    if not text or text.lower() in _INVALID_OID_STRINGS:
        raise ValueError(f"无效的{field}")
    try:
        return ObjectId(text)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"无效的{field}") from exc


def oid(value: str) -> ObjectId:
    return parse_object_id(value)

def serialize(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            result["id"] = str(value)
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [
                serialize(item) if isinstance(item, dict) else str(item) if isinstance(item, ObjectId) else item
                for item in value
            ]
        elif isinstance(value, dict):
            result[key] = serialize(value)
        else:
            result[key] = value
    return result
