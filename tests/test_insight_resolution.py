from datetime import date

from app.db import local_day
from app.services.insight_resolution import resolve_tranche


def test_week_bounds_monday_sunday() -> None:
    # 2026-01-14 Wed
    w = date(2026, 1, 14)
    mon, sun = local_day.week_bounds_containing(w)
    assert mon == date(2026, 1, 12) and sun == date(2026, 1, 18)


def test_last_day_of_month_feb_2024_leap() -> None:
    d = date(2024, 2, 29)
    assert local_day.is_last_day_of_month(d)
    d2 = date(2023, 2, 28)
    assert local_day.is_last_day_of_month(d2)


def test_resolve_tranche_end_of_month() -> None:
    assert resolve_tranche(date(2023, 10, 31)) == "month"


def test_sunday_end_of_month_prefers_month() -> None:
    # 2010-01-31 为周日 + 自然月最后一日 → 月窗
    assert resolve_tranche(date(2010, 1, 31)) == "month"


def test_resolve_tranche_sunday() -> None:
    d = date(2026, 1, 11)  # Sunday, not end of Jan
    assert resolve_tranche(d) == "week"


def test_resolve_tranche_weekday() -> None:
    d = date(2026, 1, 12)  # Mon
    assert resolve_tranche(d) == "daily"
