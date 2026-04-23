from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.local_day import (
    first_day_of_month,
    last_day_of_month,
    today_local,
    week_bounds_containing,
    yesterday_local,
)
from app.models.user_insight_summary import UserInsightSummary
from app.prompts.insight_summary import build_user_payload
from app.schemas.insight import HomeInsightData, HomeInsightPeriod, InsightTag
from app.services import insight_counting
from app.services.insight_counting import (
    day_has_intake_or_burn,
    format_burn_bullets,
    format_intake_bullets,
    load_burn_rows_in_range,
    load_intake_rows_in_range,
)
from app.services.insight_llm import generate_insight_desc_tags
from app.services.insight_resolution import resolve_tranche

logger = logging.getLogger(__name__)

INSIGHT_DAILY = "daily"
INSIGHT_WEEK = "week"
INSIGHT_MONTH = "month"
MIN_DAYS_WEEK = 5
MIN_DAYS_MONTH = 20

PLACEHOLDER_NO_LOG = "昨日暂无饮食与运动记录。补充记录后我会为你生成本地化总结与标签。"


async def get_summary_row(
    db: AsyncSession, user_id: int, insight_type: str, period_start: date
) -> UserInsightSummary | None:
    r = await db.execute(
        select(UserInsightSummary).where(
            UserInsightSummary.user_id == user_id,
            UserInsightSummary.insight_type == insight_type,
            UserInsightSummary.period_start == period_start,
        )
    )
    return r.scalar_one_or_none()


def _tags_from_row(row: UserInsightSummary) -> list[InsightTag]:
    raw = row.tags if row.tags is not None else []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    return [InsightTag.model_validate(t) for t in raw] if raw else []


def _row_to_home(row: UserInsightSummary) -> HomeInsightData:
    t = row.insight_type
    it: str = "month" if t == INSIGHT_MONTH else "week" if t == INSIGHT_WEEK else "daily"
    if it == "daily":
        # 统计仍按昨日入库；卡片日期展示用户查看当日（本地）
        tday = today_local()
        hint = _label_hint_daily_card()
        p0, p1 = tday, tday
    else:
        hint = _label_hint(row.period_start, row.period_end, it)
        p0, p1 = row.period_start, row.period_end
    return HomeInsightData(
        insight_type=it,  # type: ignore[arg-type]
        period=HomeInsightPeriod(
            period_start=p0,
            period_end=p1,
            label_hint=hint,
        ),
        desc=row.body,
        tags=_tags_from_row(row),
    )


def _label_hint(p0: date, p1: date, kind: str) -> str:
    if kind == "month":
        return f"{p0.year} 年 {p0.month} 月总结"
    if kind == "week":
        return f"本周 {p0:%m/%d}–{p1:%m/%d}"
    return _label_hint_daily_card()


def _label_hint_daily_card() -> str:
    t = today_local()
    return f"当天 {t.month}/{t.day}"


def _static_daily(y: date, desc: str, tags: list[InsightTag] | None = None) -> HomeInsightData:
    tday = today_local()
    return HomeInsightData(
        insight_type="daily",
        period=HomeInsightPeriod(
            period_start=tday,
            period_end=tday,
            label_hint=_label_hint_daily_card(),
        ),
        desc=desc,
        tags=tags or [],
    )


async def _save_ok(
    db: AsyncSession,
    user_id: int,
    kind: str,
    period_start: date,
    period_end: date,
    body: str,
    tags: list[dict],
    distinct_days: int | None,
) -> None:
    row = await get_summary_row(db, user_id, kind, period_start)
    if row is None:
        row = UserInsightSummary(
            user_id=user_id,
            insight_type=kind,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(row)
    row.period_end = period_end
    row.body = body
    row.tags = tags
    row.status = "ok"
    row.error_message = None
    row.intake_distinct_days = distinct_days
    await db.commit()
    await db.refresh(row)


async def _save_failed(
    db: AsyncSession,
    user_id: int,
    kind: str,
    period_start: date,
    period_end: date,
    err: str,
) -> None:
    row = await get_summary_row(db, user_id, kind, period_start)
    if row is None:
        row = UserInsightSummary(
            user_id=user_id,
            insight_type=kind,
            period_start=period_start,
            period_end=period_end,
            body="",
            tags=[],
        )
        db.add(row)
    row.status = "failed"
    row.error_message = err
    await db.commit()


async def _llm_for_range(
    db: AsyncSession,
    user_id: int,
    *,
    kind: str,
    period_text: str,
    start_d: date,
    end_d: date,
) -> tuple[str, list[dict], int | None]:
    intakes = await load_intake_rows_in_range(db, user_id, start_d, end_d)
    burns = await load_burn_rows_in_range(db, user_id, start_d, end_d)
    n_days = await insight_counting.count_distinct_intake_days_in_range(db, user_id, start_d, end_d)
    u = build_user_payload(
        kind=kind,
        period_text=period_text,
        intake_bullets=format_intake_bullets(intakes),
        burn_bullets=format_burn_bullets(burns),
    )
    desc, tags = await generate_insight_desc_tags(u)
    return desc, tags, n_days


async def _try_month(
    db: AsyncSession, user_id: int, today: date
) -> HomeInsightData | None:
    m0, m1 = first_day_of_month(today), last_day_of_month(today)
    n = await insight_counting.count_distinct_intake_days_in_range(db, user_id, m0, m1)
    if n < MIN_DAYS_MONTH:
        return None
    row = await get_summary_row(db, user_id, INSIGHT_MONTH, m0)
    if row and row.status == "ok" and row.body:
        return _row_to_home(row)
    try:
        desc, tags, n_days = await _llm_for_range(
            db,
            user_id,
            kind="month",
            period_text=f"{m0.isoformat()} 至 {m1.isoformat()}",
            start_d=m0,
            end_d=m1,
        )
        await _save_ok(db, user_id, INSIGHT_MONTH, m0, m1, desc, tags, n_days)
    except Exception as e:  # noqa: BLE001
        logger.exception("month insight failed")
        await _save_failed(db, user_id, INSIGHT_MONTH, m0, m1, str(e))
        return None
    row2 = await get_summary_row(db, user_id, INSIGHT_MONTH, m0)
    return _row_to_home(row2) if row2 and row2.status == "ok" else None


async def _try_week(db: AsyncSession, user_id: int, today: date) -> HomeInsightData | None:
    w0, w1 = week_bounds_containing(today)
    n = await insight_counting.count_distinct_intake_days_in_range(db, user_id, w0, w1)
    if n < MIN_DAYS_WEEK:
        return None
    row = await get_summary_row(db, user_id, INSIGHT_WEEK, w0)
    if row and row.status == "ok" and row.body:
        return _row_to_home(row)
    try:
        desc, tags, n_days = await _llm_for_range(
            db,
            user_id,
            kind="week",
            period_text=f"{w0.isoformat()} 至 {w1.isoformat()} (周一至周日)",
            start_d=w0,
            end_d=w1,
        )
        await _save_ok(db, user_id, INSIGHT_WEEK, w0, w1, desc, tags, n_days)
    except Exception as e:  # noqa: BLE001
        logger.exception("week insight failed")
        await _save_failed(db, user_id, INSIGHT_WEEK, w0, w1, str(e))
        return None
    row2 = await get_summary_row(db, user_id, INSIGHT_WEEK, w0)
    return _row_to_home(row2) if row2 and row2.status == "ok" else None


async def _build_daily(db: AsyncSession, user_id: int, y: date) -> HomeInsightData:
    intakes = await load_intake_rows_in_range(db, user_id, y, y)
    burns = await load_burn_rows_in_range(db, user_id, y, y)
    if not day_has_intake_or_burn(intakes, burns):
        return _static_daily(y, PLACEHOLDER_NO_LOG, [])

    row = await get_summary_row(db, user_id, INSIGHT_DAILY, y)
    if row and row.status == "ok" and row.body:
        return _row_to_home(row)
    try:
        desc, tags, n_days = await _llm_for_range(
            db,
            user_id,
            kind="daily",
            period_text=f"{y.isoformat()} (昨日，上海时区)",
            start_d=y,
            end_d=y,
        )
        await _save_ok(db, user_id, INSIGHT_DAILY, y, y, desc, tags, n_days)
    except Exception as e:  # noqa: BLE001
        logger.exception("daily insight failed")
        await _save_failed(db, user_id, INSIGHT_DAILY, y, y, str(e))
        return _static_daily(y, f"总结暂不可用：{e!s}。请稍后重试。", [])

    row2 = await get_summary_row(db, user_id, INSIGHT_DAILY, y)
    return _row_to_home(row2) if row2 and row2.status == "ok" else _static_daily(y, "总结暂不可用，请稍后再试。", [])


async def build_home_insight(db: AsyncSession, user_id: int) -> HomeInsightData:
    today = today_local()
    y = yesterday_local()
    t = resolve_tranche(today)

    if t == "month":
        m = await _try_month(db, user_id, today)
        if m is not None:
            return m
        if today.weekday() == 6:
            w = await _try_week(db, user_id, today)
            if w is not None:
                return w
        return await _build_daily(db, user_id, y)

    if t == "week":
        w = await _try_week(db, user_id, today)
        if w is not None:
            return w
        return await _build_daily(db, user_id, y)

    return await _build_daily(db, user_id, y)
