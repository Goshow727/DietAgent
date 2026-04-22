from datetime import date, datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.banner_agent import generate_card_drafts, generate_image_and_upload
from app.models.intake_log import IntakeLog
from app.models.burn_log import BurnLog
from app.models.recommendation_card import RecommendationCard
from app.models.user import User
from app.services import rag_service
from app.services.user_body_context import format_user_body_context

POOL_THRESHOLD = 8
_HIGH_SALT_FOOD_KEYWORDS = ["腌", "咸", "泡菜", "酱", "火锅", "薯片", "培根"]


async def _ready_count(user_id: int, db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(RecommendationCard).where(
        RecommendationCard.user_id == user_id,
        RecommendationCard.status == "ready",
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def _get_last7_intake(user_id: int, db: AsyncSession) -> list[IntakeLog]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(IntakeLog)
        .where(IntakeLog.user_id == user_id, IntakeLog.logged_at >= cutoff)
        .order_by(IntakeLog.logged_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_last7_burn(user_id: int, db: AsyncSession) -> list[BurnLog]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(BurnLog)
        .where(BurnLog.user_id == user_id, BurnLog.logged_at >= cutoff)
        .order_by(BurnLog.logged_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _intake_summary(logs: list[IntakeLog]) -> str:
    if not logs:
        return "近7天无饮食记录"
    lines = [f"- {l.food_name} {l.weight_grams:.0f}g ({l.kcal:.0f}kcal)" for l in logs[:15]]
    return "\n".join(lines)


def _burn_summary(logs: list[BurnLog]) -> str:
    if not logs:
        return "近7天无运动记录"
    lines = [f"- {l.exercise_type} {l.duration_minutes}分钟 ({l.kcal:.0f}kcal)" for l in logs]
    return "\n".join(lines)


def _derive_rag_categories(
    intake_logs: list[IntakeLog], burn_logs: list[BurnLog]
) -> list[str]:
    total_kcal = sum(l.kcal for l in intake_logs) or 1
    total_fat_kcal = sum(l.fat_g * 9 for l in intake_logs)
    total_protein_kcal = sum(l.protein_g * 4 for l in intake_logs)
    avg_fat_pct = (total_fat_kcal / total_kcal) * 100
    avg_protein_pct = (total_protein_kcal / total_kcal) * 100

    burn_dates = {l.logged_at.date() for l in burn_logs if l.logged_at}
    all_days = {(date.today() - timedelta(days=i)) for i in range(7)}
    days_without_burn = len(all_days - burn_dates)

    has_high_salt = any(
        kw in l.food_name for l in intake_logs for kw in _HIGH_SALT_FOOD_KEYWORDS
    )

    return rag_service.derive_categories(
        avg_fat_pct=avg_fat_pct,
        avg_protein_pct=avg_protein_pct,
        days_without_burn=days_without_burn,
        has_high_salt=has_high_salt,
    )


async def _red_cut_titles(user_id: int, db: AsyncSession) -> list[str]:
    stmt = select(RecommendationCard.title).where(
        RecommendationCard.user_id == user_id,
        RecommendationCard.status == "red_cut",
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def generate_cards(user_id: int, count: int, db: AsyncSession) -> None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    intake_logs = await _get_last7_intake(user_id, db)
    burn_logs = await _get_last7_burn(user_id, db)
    red_cut = await _red_cut_titles(user_id, db)
    categories = _derive_rag_categories(intake_logs, burn_logs)

    query_text = _intake_summary(intake_logs)[:200] + " " + _burn_summary(burn_logs)[:100]

    try:
        chunks = await rag_service.retrieve(
            query=query_text, categories=categories, top_k=5, db=db
        )
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        chunks = []

    try:
        drafts = await generate_card_drafts(
            guideline_chunks=chunks,
            user_body_block=format_user_body_context(user),
            intake_summary=_intake_summary(intake_logs),
            burn_summary=_burn_summary(burn_logs),
            red_cut_titles=red_cut,
            count=count,
        )
    except Exception as e:
        logger.error(f"Banner content generation failed for user {user_id}: {e}")
        return

    for draft in drafts:
        card = RecommendationCard(
            user_id=user_id,
            title=(draft.get("title") or "")[:200],
            desc=draft.get("desc") or "",
            image_prompt=draft.get("image_prompt"),
            category=draft.get("category", "diet"),
            status="queued",
        )
        db.add(card)
        await db.commit()
        await db.refresh(card)

        image_url = None
        if card.image_prompt:
            image_url = await generate_image_and_upload(card.image_prompt)

        card.image_url = image_url
        card.status = "ready"
        await db.commit()


async def ensure_pool(user_id: int, db: AsyncSession) -> None:
    count = await _ready_count(user_id, db)
    deficit = POOL_THRESHOLD - count
    if deficit > 0:
        await generate_cards(user_id=user_id, count=deficit, db=db)


async def get_ready_cards(user_id: int, count: int, db: AsyncSession) -> list[RecommendationCard]:
    stmt = (
        select(RecommendationCard)
        .where(
            RecommendationCard.user_id == user_id,
            RecommendationCard.status == "ready",
        )
        .order_by(RecommendationCard.created_at.asc())
        .limit(count)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def red_cut_card(card_id: str, user_id: int, db: AsyncSession) -> RecommendationCard | None:
    stmt = select(RecommendationCard).where(
        RecommendationCard.id == card_id,
        RecommendationCard.user_id == user_id,
    )
    result = await db.execute(stmt)
    card = result.scalar_one_or_none()
    if card is None:
        return None
    card.status = "red_cut"
    card.red_cut_at = datetime.now(timezone.utc)
    await db.commit()
    return card


async def next_ready_card(user_id: int, db: AsyncSession) -> RecommendationCard | None:
    stmt = (
        select(RecommendationCard)
        .where(
            RecommendationCard.user_id == user_id,
            RecommendationCard.status == "ready",
        )
        .order_by(RecommendationCard.created_at.asc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
