from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.serialize import serialize

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(payload: LoginRequest):
    db = get_db()
    user_service = UserService(db)
    user = await user_service.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    access = AuthService.create_access_token(user["username"])
    refresh = AuthService.create_refresh_token(user["username"])
    return ok(
        {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 86400,
            "user": await user_service.public_user(user),
        }
    )


@router.post("/refresh")
async def refresh(payload: RefreshRequest):
    token_data = AuthService.verify_token(payload.refresh_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="刷新令牌无效")
    access = AuthService.create_access_token(token_data.sub)
    return ok({"access_token": access, "token_type": "bearer", "expires_in": 86400})


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return ok(await UserService(get_db()).public_user(user))


@router.post("/logout")
async def logout(_user=Depends(get_current_user)):
    return ok({"logged_out": True})
