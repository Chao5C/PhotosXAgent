from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_db, get_db, init_db
from app.core.response import fail
from app.routers import albums, auth, chat, config, health, journey, llm, photos, recommendations
from app.services.llm_config_service import LLMConfigService
from app.services.user_service import UserService
from photosx.llm.client import refresh_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("photosx")


def get_version() -> str:
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("PhotosXAgent starting...")
    await init_db()
    await UserService(get_db()).ensure_default_admin()
    await LLMConfigService(get_db()).ensure_defaults()
    await refresh_runtime()
    yield
    await close_db()
    logger.info("PhotosXAgent stopped")


app = FastAPI(title="PhotosXAgent", version=get_version(), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content=fail(str(exc.detail), exc.status_code))
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content=fail(str(exc), 500))


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(photos.router)
app.include_router(albums.router)
app.include_router(journey.router)
app.include_router(recommendations.router)
app.include_router(chat.router)
app.include_router(config.router)
app.include_router(llm.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
