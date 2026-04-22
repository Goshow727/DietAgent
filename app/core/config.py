from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "dietAgent"
    DEBUG: bool = False

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/dietagent"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    JWT_SECRET: str = Field(default="change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    OSS_ACCESS_KEY_ID: str = "REMOVED_OSS_KEY_ID"
    OSS_ACCESS_KEY_SECRET: str = "REMOVED_OSS_KEY_SECRET"
    OSS_ENDPOINT: str = "oss-cn-guangzhou.aliyuncs.com"
    OSS_BUCKET: str = "test-zsp-oss"
    OSS_BASE_URL: str = "https://test-zsp-oss.oss-cn-guangzhou.aliyuncs.com"

    NLS_APP_KEY: str = "nuaHPUJwH1r9l6Ch"
    NLS_ACCESS_KEY_ID: str = ""
    NLS_ACCESS_KEY_SECRET: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
