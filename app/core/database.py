import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from redis.asyncio import Redis

from .config import settings

logger = logging.getLogger(__name__)

mongo_client: Optional[AsyncIOMotorClient] = None
mongo_db: Optional[AsyncIOMotorDatabase] = None
redis_client: Optional[Redis] = None


async def init_db() -> None:
    global mongo_client, mongo_db, redis_client

    mongo_client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_db = mongo_client[settings.MONGODB_DATABASE]
    await mongo_client.admin.command("ping")
    logger.info("MongoDB connected: %s", settings.MONGODB_DATABASE)

    await mongo_db.users.create_index("username", unique=True)
    await mongo_db.photos.create_index([("user_id", 1), ("created_at", -1)])
    await mongo_db.albums.create_index([("user_id", 1), ("kind", 1)])
    await mongo_db.recommendations.create_index([("user_id", 1), ("created_at", -1)])
    await mongo_db.chat_messages.create_index([("user_id", 1), ("created_at", 1)])

    try:
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        await redis_client.ping()
        logger.info("Redis connected")
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to in-process tasks: %s", exc)
        redis_client = None


async def close_db() -> None:
    global mongo_client, redis_client
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()


def get_db() -> AsyncIOMotorDatabase:
    if mongo_db is None:
        raise RuntimeError("Database not initialized")
    return mongo_db
