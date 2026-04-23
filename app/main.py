import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import TraceIdMiddleware
from app.db.redis import close_redis
from app.db.session import AsyncSessionLocal
from app.services import banner_service


async def _red_cut_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(settings.BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                n = await banner_service.cleanup_expired_red_cut_cards(db)
                if n:
                    logger.info("red-cut cleanup removed {} rows", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("red-cut cleanup loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"{settings.APP_NAME} starting... debug={settings.DEBUG}")
    cleanup_task = asyncio.create_task(_red_cut_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await close_redis()
        logger.info(f"{settings.APP_NAME} stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
