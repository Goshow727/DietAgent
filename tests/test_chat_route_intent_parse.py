import json

import pytest

from app.agents.diet_agent import parse_intent_route_json
from app.schemas.chat_intent import ChatRouteIntent


@pytest.mark.parametrize("intent_str", ["update_body_metrics", "update_preferences"])
def test_parse_extended_intents(intent_str: str) -> None:
    raw = json.dumps({"intent": intent_str})
    got = parse_intent_route_json(raw)
    assert got.intent == ChatRouteIntent(intent_str)
