from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.local_day import INSIGHT_TZ, local_date_at, local_inclusive_utc_range
from app.models.burn_log import BurnLog
from app.models.intake_log import IntakeLog


async def count_distinct_intake_days_in_range(
    db: AsyncSession, user_id: int, start_d: date, end_d: date
) -> int:
    start_utc, end_utc = local_inclusive_utc_range(start_d, end_d)
    r = await db.execute(
        select(IntakeLog.logged_at).where(
            IntakeLog.user_id == user_id,
            IntakeLog.logged_at >= start_utc,
            IntakeLog.logged_at < end_utc,
        )
    )
    local_days = {local_date_at(x) for x in r.scalars().all()}
    return len(local_days)


async def load_intake_rows_in_range(
    db: AsyncSession, user_id: int, start_d: date, end_d: date
) -> Sequence[IntakeLog]:
    start_utc, end_utc = local_inclusive_utc_range(start_d, end_d)
    r = await db.execute(
        select(IntakeLog)
        .where(
            IntakeLog.user_id == user_id,
            IntakeLog.logged_at >= start_utc,
            IntakeLog.logged_at < end_utc,
        )
        .order_by(IntakeLog.logged_at)
    )
    return r.scalars().all()


async def load_burn_rows_in_range(
    db: AsyncSession, user_id: int, start_d: date, end_d: date
) -> Sequence[BurnLog]:
    start_utc, end_utc = local_inclusive_utc_range(start_d, end_d)
    r = await db.execute(
        select(BurnLog)
        .where(
            BurnLog.user_id == user_id,
            BurnLog.logged_at >= start_utc,
            BurnLog.logged_at < end_utc,
        )
        .order_by(BurnLog.logged_at)
    )
    return r.scalars().all()


def format_intake_bullets(rows: Sequence[IntakeLog]) -> str:
    if not rows:
        return "（无摄入记录）"
    lines: list[str] = []
    for r in rows[:80]:
        lines.append(
            f"- {r.food_name}，约 {r.weight_grams}g，蛋白/碳水/脂 {r.protein_g:.1f}/{r.carb_g:.1f}/{r.fat_g:.1f}g，kcal {r.kcal:.0f}"
        )
    if len(rows) > 80:
        lines.append(f"… 共 {len(rows)} 条，仅列前 80 条。")
    return "\n".join(lines)


def format_burn_bullets(rows: Sequence[BurnLog]) -> str:
    if not rows:
        return "（无运动记录）"
    lines: list[str] = []
    for r in rows[:50]:
        et = "有氧" if r.exercise_type == "cardio" else "无氧"
        lines.append(
            f"- {et}，强度{r.intensity}，{r.duration_minutes} 分钟，约 {r.kcal:.0f} kcal"
        )
    if len(rows) > 50:
        lines.append(f"… 共 {len(rows)} 条，仅列前 50 条。")
    return "\n".join(lines)


def day_has_intake_or_burn(intake_rows: Sequence[IntakeLog], burn_rows: Sequence[BurnLog]) -> bool:
    return bool(intake_rows) or bool(burn_rows)
