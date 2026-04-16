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


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"{settings.APP_NAME} starting... debug={settings.DEBUG}")
    yield
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
