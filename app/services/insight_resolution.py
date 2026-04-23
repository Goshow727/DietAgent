from datetime import date
from typing import Literal

from app.db.local_day import is_last_day_of_month


def resolve_tranche(today: date) -> Literal["month", "week", "daily"]:
    """先月末窗，再周日窗，否则日。"""
    if is_last_day_of_month(today):
        return "month"
    if today.weekday() == 6:  # Sunday
        return "week"
    return "daily"
