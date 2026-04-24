import json

from app.agents.diet_agent import parse_body_metrics_json, parse_preference_json
from app.schemas.body_patch import BodyMetricsFlow
from app.schemas.preference_extraction import PreferenceFlow


def test_parse_body_metrics_ready_minimal() -> None:
    raw = json.dumps(
        {
            "flow": "ready",
            "clarify_message": "",
            "patch": {"height": 175.0, "weight": None, "age": None, "gender": None},
        }
    )
    got = parse_body_metrics_json(raw)
    assert got.flow == BodyMetricsFlow.ready
    assert got.patch is not None and got.patch.height == 175.0


def test_parse_preference_ready_one_item() -> None:
    raw = json.dumps(
        {
            "flow": "ready",
            "clarify_message": "",
            "items": [{"category": "dislike", "raw_text": "不吃香菜"}],
        }
    )
    got = parse_preference_json(raw)
    assert got.flow == PreferenceFlow.ready
    assert len(got.items) == 1
    assert got.items[0].raw_text == "不吃香菜"
