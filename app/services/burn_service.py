from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.db.local_day import local_inclusive_utc_range
from app.models.burn_log import BurnLog
from app.schemas.food import BurnLogCreate


async def create_burn(db: AsyncSession, user_id: int, payload: BurnLogCreate) -> BurnLog:
    log = BurnLog(
        user_id=user_id,
        exercise_type=payload.exercise_type,
        intensity=payload.intensity,
        duration_minutes=payload.duration_minutes,
        kcal=payload.kcal,
        logged_at=payload.logged_at,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def list_burns(db: AsyncSession, user_id: int, log_date: date) -> list[BurnLog]:
    start, end = local_inclusive_utc_range(log_date, log_date)
    result = await db.execute(
        select(BurnLog)
        .where(BurnLog.user_id == user_id, BurnLog.logged_at >= start, BurnLog.logged_at < end)
        .order_by(BurnLog.logged_at)
    )
    return list(result.scalars().all())


async def delete_burn(db: AsyncSession, user_id: int, burn_id: int) -> None:
    log = await db.get(BurnLog, burn_id)
    if not log or log.user_id != user_id:
        raise BusinessException(ErrorCode.LOG_NOT_FOUND)
    await db.delete(log)
    await db.commit()
