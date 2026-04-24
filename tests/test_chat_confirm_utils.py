import pytest

from app.services.chat_confirm_utils import parse_confirm_intent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("确认", "confirm"),
        ("取消", "cancel"),
        ("好的", "confirm"),
        ("no", "cancel"),
        ("随便说说", None),
    ],
)
def test_parse_confirm_intent(text: str, expected: str | None) -> None:
    assert parse_confirm_intent(text) == expected
