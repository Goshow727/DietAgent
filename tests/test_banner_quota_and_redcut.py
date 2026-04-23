from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from zoneinfo import ZoneInfo

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.db.local_day import INSIGHT_TZ, next_shanghai_midnight_after
from app.services import banner_service


def test_next_shanghai_midnight_after() -> None:
    d = date(2026, 4, 23)
    mid = next_shanghai_midnight_after(d)
    assert mid.tzinfo == INSIGHT_TZ
    assert mid == datetime(2026, 4, 24, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.asyncio
async def test_consume_banner_get_quota_rejects_when_no_returning_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        BANNER_GET_DAILY_LIMIT = 20

    monkeypatch.setattr(banner_service, "settings", _S())

    exec_result = MagicMock()
    exec_result.first = MagicMock(return_value=None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=exec_result)
    db.scalar = AsyncMock(return_value=20)

    with pytest.raises(BusinessException) as ei:
        await banner_service.consume_banner_get_quota(1, db)
    assert ei.value.code == ErrorCode.BANNER_GET_RATE_LIMITED
    assert ei.value.data["limit"] == 20
    assert ei.value.data["used"] == 20
    assert "resets_at" in ei.value.data
