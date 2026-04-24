from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_preference import UserPreference


async def add_preferences(
    db: AsyncSession, user_id: int, items: list[tuple[str, str]]
) -> None:
    for category, raw_text in items:
        db.add(
            UserPreference(user_id=user_id, category=category, raw_text=raw_text)
        )
    await db.commit()


async def list_raw_texts_for_user(
    db: AsyncSession, user_id: int, limit: int = 50
) -> list[str]:
    result = await db.execute(
        select(UserPreference.raw_text)
        .where(UserPreference.user_id == user_id)
        .order_by(UserPreference.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
