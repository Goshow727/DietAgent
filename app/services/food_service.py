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


async def create_food_from_estimate(
    db: AsyncSession,
    name: str,
    kcal_per_100g: float,
    protein_per_100g: float,
    carb_per_100g: float,
    fat_per_100g: float,
) -> Food:
    """为照片估计等场景插入一条可复用的 `foods` 行，再用于 `intake_logs` 外键。"""
    food = Food(
        name=name[:128],
        kcal_per_100g=kcal_per_100g,
        protein_per_100g=protein_per_100g,
        carb_per_100g=carb_per_100g,
        fat_per_100g=fat_per_100g,
    )
    db.add(food)
    await db.commit()
    await db.refresh(food)
    return food
