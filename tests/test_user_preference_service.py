import pytest

from app.models.user import User
from app.services import user_preference_service
from app.services.user_body_context import (
    format_user_body_context,
    format_user_context_for_model,
)


def test_format_user_body_context_unchanged() -> None:
    u = User(
        id=1,
        username="u1",
        hashed_password="x",
        height=170.0,
        weight=65.0,
        age=30,
        gender="男",
    )
    out = format_user_body_context(u)
    assert "170" in out and "cm" in out
    assert "65" in out and "kg" in out


@pytest.mark.asyncio
async def test_format_user_context_uses_pref_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(db, user_id: int, limit: int = 50):
        return ["不吃香菜"]

    monkeypatch.setattr(
        user_preference_service,
        "list_raw_texts_for_user",
        fake_list,
    )
    u = User(id=2, username="u2", hashed_password="y")
    out = await format_user_context_for_model(None, u)
    assert "不吃香菜" in out
    assert "【饮食偏好与忌口】" in out
