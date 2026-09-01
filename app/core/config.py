from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import List


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DEBUG: bool = Field(default=True)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    MONGODB_HOST: str = Field(default="localhost")
    MONGODB_PORT: int = Field(default=27017)
    MONGODB_USERNAME: str = Field(default="")
    MONGODB_PASSWORD: str = Field(default="")
    MONGODB_DATABASE: str = Field(default="photosxagent")
    MONGODB_AUTH_SOURCE: str = Field(default="admin")

    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=1)

    JWT_SECRET: str = Field(default="photosxagent-change-this-secret-key-32b")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    DEFAULT_ADMIN_USERNAME: str = Field(default="admin")
    DEFAULT_ADMIN_PASSWORD: str = Field(default="admin123")

    LLM_PROVIDER: str = Field(default="qwen")
    LLM_VISION_MODEL: str = Field(default="qwen-vl-max")
    LLM_TEXT_MODEL: str = Field(default="qwen-plus")
    OPENAI_API_KEY: str = Field(default="")
    DASHSCOPE_API_KEY: str = Field(default="")
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com")
    VOLCENGINE_API_KEY: str = Field(default="")
    VOLCENGINE_BASE_URL: str = Field(default="https://ark.cn-beijing.volces.com/api/v3")
    VOLCENGINE_CODING_API_KEY: str = Field(default="")
    VOLCENGINE_CODING_BASE_URL: str = Field(default="https://ark.cn-beijing.volces.com/api/coding/v3")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434/v1")
    OLLAMA_MODEL: str = Field(default="llama3.1")
    CUSTOM_OPENAI_API_KEY: str = Field(default="")
    CUSTOM_OPENAI_BASE_URL: str = Field(default="")
    AMAP_WEB_KEY: str = Field(default="", description="高德 Web 服务 Key，用于国内逆地理编码")

    DISTANCE_THRESHOLD_KM: float = Field(default=50.0)
    UPLOAD_DIR: str = Field(default="data/uploads")
    TOPICS_DIR: str = Field(default="data/topics")
    MAX_UPLOAD_SIZE: int = Field(default=30 * 1024 * 1024)
    TIMEZONE: str = Field(default="Asia/Shanghai")
    STUDIO_VOICE_ID: str = Field(default="default")
    STUDIO_TTS_ENABLED: bool = Field(default=False)

    @property
    def MONGO_URI(self) -> str:
        if self.MONGODB_USERNAME and self.MONGODB_PASSWORD:
            return (
                f"mongodb://{self.MONGODB_USERNAME}:{self.MONGODB_PASSWORD}"
                f"@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DATABASE}"
                f"?authSource={self.MONGODB_AUTH_SOURCE}"
            )
        return f"mongodb://{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DATABASE}"

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def topics_path(self) -> Path:
        path = Path(self.TOPICS_DIR)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
