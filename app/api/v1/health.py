from fastapi import APIRouter
from loguru import logger
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.response import R
from app.db.redis import get_redis_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=R[dict])
async def health(db: DbSession) -> R[dict]:
    status = {"db": "ok", "redis": "ok"}
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"db check failed: {e}")
        status["db"] = f"error: {e}"
    try:
        client = get_redis_client()
        await client.ping()
    except Exception as e:
        logger.warning(f"redis check failed: {e}")
        status["redis"] = f"error: {e}"
    return R.ok(status)
