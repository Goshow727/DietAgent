from datetime import date, datetime, time, timezone


def day_range_utc(d: date) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes covering the full calendar day `d`."""
    start = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
    end = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)
    return start, end
