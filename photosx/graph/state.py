from typing import Any, List, Optional, TypedDict


class PhotoAgentState(TypedDict, total=False):
    user_id: str
    photo_id: str
    file_path: str
    metadata: dict
    vision: dict
    geo: dict
    albums: List[str]
    recommendation: Optional[dict]
    error: Optional[str]


class ChatAgentState(TypedDict, total=False):
    user_id: str
    message: str
    history: List[dict]
    context: dict
    reply: str
    citations: List[Any]
    provider: str
    model_name: str
    photo_ids: List[str]
    top_k: int
    intent: str
    photos: List[dict]
    albums: List[dict]
    total: int
    has_more: bool
    query_id: str
    kind: str
    reminder: dict
    poster: dict
    guide: dict
