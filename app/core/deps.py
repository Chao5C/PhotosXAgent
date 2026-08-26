from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.core.database import get_db
from app.services.auth_service import AuthService
from app.services.user_service import UserService


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    token = authorization.split(" ", 1)[1]
    token_data = AuthService.verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    db = get_db()
    user = await UserService(db).get_by_username(token_data.sub)
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user
