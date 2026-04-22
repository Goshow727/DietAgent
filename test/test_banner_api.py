import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.deps import get_current_user, get_db


def _make_card(card_id="abc", title="测试卡片", status="ready"):
    card = MagicMock()
    card.id = card_id
    card.title = title
    card.desc = "描述内容"
    card.image_url = None
    card.category = "diet"
    card.status = status
    return card


@pytest.mark.asyncio
async def test_get_banners_returns_cards():
    mock_user = MagicMock(id=1, is_active=True)

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.api.v1.banner.banner_service.get_ready_cards", new_callable=AsyncMock) as mock_get, \
             patch("app.api.v1.banner.banner_service.ready_count", new_callable=AsyncMock) as mock_count:

            mock_get.return_value = [_make_card()]
            mock_count.return_value = 8

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/banners?count=3",
                    headers={"Authorization": "Bearer test-token"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert len(data["data"]["cards"]) == 1


@pytest.mark.asyncio
async def test_red_cut_returns_404_when_card_not_found():
    from app.api.deps import get_current_user, get_db

    mock_db = AsyncMock()
    mock_user = MagicMock(id=1)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("app.api.v1.banner.banner_service.red_cut_card", new_callable=AsyncMock) as mock_red_cut:
            mock_red_cut.return_value = None

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.put(
                    "/api/v1/banners/nonexistent-id/red-cut",
                    headers={"Authorization": "Bearer test-token"},
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 10004
