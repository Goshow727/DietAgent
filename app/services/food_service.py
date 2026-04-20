from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.models.food import Food


async def search_foods(db: AsyncSession, q: str) -> list[Food]:
    result = await db.execute(
        select(Food).where(Food.name.ilike(f"%{q}%")).limit(20)
    )
    return list(result.scalars().all())


async def get_food_by_id(db: AsyncSession, food_id: int) -> Food:
    food = await db.get(Food, food_id)
    if not food:
        raise BusinessException(ErrorCode.FOOD_NOT_FOUND)
    return food
