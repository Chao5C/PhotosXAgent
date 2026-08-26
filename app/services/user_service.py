from typing import Optional

import bcrypt
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.utils.serialize import utcnow


class UserService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.users

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    async def ensure_default_admin(self) -> None:
        existing = await self.collection.find_one({"username": settings.DEFAULT_ADMIN_USERNAME})
        if existing:
            return
        now = utcnow()
        await self.collection.insert_one(
            {
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "email": "admin@photosx.local",
                "hashed_password": self.hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                "is_active": True,
                "is_admin": True,
                "created_at": now,
                "updated_at": now,
            }
        )

    async def get_by_username(self, username: str) -> Optional[dict]:
        return await self.collection.find_one({"username": username})

    async def authenticate(self, username: str, password: str) -> Optional[dict]:
        user = await self.get_by_username(username)
        if not user or not self.verify_password(password, user.get("hashed_password", "")):
            return None
        if not user.get("is_active", True):
            return None
        await self.collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": utcnow()}})
        return user

    async def public_user(self, user: dict) -> dict:
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user.get("email", ""),
            "is_admin": bool(user.get("is_admin")),
            "is_active": bool(user.get("is_active", True)),
            "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
        }
