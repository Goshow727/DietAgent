"""MVP 固定 Asia/Shanghai，与产品规格「本地日界」一致。"""

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

INSIGHT_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


def now_local() -> datetime:
    return datetime.now(INSIGHT_TZ)


def today_local() -> date:
    return now_local().date()


def yesterday_local() -> date:
    return today_local() - timedelta(days=1)


def local_date_at(dt: datetime) -> date:
    """将任意 tz-aware 或 naïve(按 UTC) 的 logged_at 转为上海日历日。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(INSIGHT_TZ).date()


def first_day_of_month(d: date) -> date:
    return d.replace(day=1)


def last_day_of_month(d: date) -> date:
    last = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last)


def is_last_day_of_month(d: date) -> bool:
    return d == last_day_of_month(d)


def week_bounds_containing(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def local_inclusive_utc_range(start_d: date, end_d: date) -> tuple[datetime, datetime]:
    """[start_d 00:00, end_d 24:00) 左闭右开，用 UTC 存进查询（与 ORM 一致）。"""
    s = datetime.combine(start_d, time.min, INSIGHT_TZ)
    e = datetime.combine(end_d + timedelta(days=1), time.min, INSIGHT_TZ)
    return s.astimezone(UTC), e.astimezone(UTC)
