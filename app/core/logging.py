import sys

from loguru import logger

from app.core.config import settings

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>trace</cyan>=<magenta>{extra[trace_id]}</magenta> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging() -> None:
    logger.remove()
    logger.configure(extra={"trace_id": "-"})
    logger.add(
        sys.stdout,
        level="DEBUG" if settings.DEBUG else "INFO",
        format=_FORMAT,
        enqueue=False,
        backtrace=True,
        diagnose=settings.DEBUG,
    )
