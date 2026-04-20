from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.db.utils import day_range_utc
from app.models.intake_log import IntakeLog
from app.schemas.food import IntakeLogCreate
from app.services.food_service import get_food_by_id


async def create_intake(db: AsyncSession, user_id: int, payload: IntakeLogCreate) -> IntakeLog:
    food = await get_food_by_id(db, payload.food_id)
    ratio = payload.weight_grams / 100
    log = IntakeLog(
        user_id=user_id,
        food_id=food.id,
        food_name=food.name,
        weight_grams=payload.weight_grams,
        protein_g=round(food.protein_per_100g * ratio, 2),
        carb_g=round(food.carb_per_100g * ratio, 2),
        fat_g=round(food.fat_per_100g * ratio, 2),
        kcal=round(food.kcal_per_100g * ratio, 2),
        logged_at=payload.logged_at,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def list_intakes(db: AsyncSession, user_id: int, log_date: date) -> list[IntakeLog]:
    start, end = day_range_utc(log_date)
    result = await db.execute(
        select(IntakeLog)
        .where(IntakeLog.user_id == user_id, IntakeLog.logged_at.between(start, end))
        .order_by(IntakeLog.logged_at)
    )
    return list(result.scalars().all())


async def delete_intake(db: AsyncSession, user_id: int, intake_id: int) -> None:
    log = await db.get(IntakeLog, intake_id)
    if not log or log.user_id != user_id:
        raise BusinessException(ErrorCode.LOG_NOT_FOUND)
    await db.delete(log)
    await db.commit()
