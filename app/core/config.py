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

    # 首页/洞察总结（见 app/services/insight_llm.py）— OpenAI 兼容接口
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    ARK_API_KEY: str = ""
    ARK_VISION_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    ARK_VISION_MODEL: str = "doubao-seed-2-0-lite-260215"
    ARK_IMAGE_MODEL: str = "doubao-seedream-4-0-250828"
    ARK_IMAGE_SIZE: str = "1K"
    ARK_IMAGE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

    OSS_ACCESS_KEY_ID: str = "REMOVED_OSS_KEY_ID"
    OSS_ACCESS_KEY_SECRET: str = "REMOVED_OSS_KEY_SECRET"
    OSS_ENDPOINT: str = "oss-cn-guangzhou.aliyuncs.com"
    OSS_BUCKET: str = "test-zsp-oss"
    OSS_BASE_URL: str = "https://test-zsp-oss.oss-cn-guangzhou.aliyuncs.com"

    BANNER_GET_DAILY_LIMIT: int = 20
    BANNER_REDCUT_RETENTION_DAYS: int = 7
    BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS: int = 3600
    BANNER_REDCUT_CLEANUP_BATCH_SIZE: int = 500
    BANNER_ENABLE_NETWORK_SEARCH: bool = False

    NLS_APP_KEY: str = "nuaHPUJwH1r9l6Ch"
    NLS_ACCESS_KEY_ID: str = ""
    NLS_ACCESS_KEY_SECRET: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
