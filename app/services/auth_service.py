from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel

from app.core.config import settings


class TokenData(BaseModel):
    sub: str
    exp: int


class AuthService:
    @staticmethod
    def create_access_token(sub: str, expires_minutes: int | None = None) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        token = jwt.encode({"sub": sub, "exp": expire}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token if isinstance(token, str) else token.decode("utf-8")

    @staticmethod
    def create_refresh_token(sub: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {"sub": sub, "exp": expire, "type": "refresh"},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        return token if isinstance(token, str) else token.decode("utf-8")

    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            return TokenData(sub=payload.get("sub"), exp=int(payload.get("exp", 0)))
        except Exception:
            return None
