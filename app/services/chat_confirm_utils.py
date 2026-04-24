"""用户自然语言「确认 / 取消」解析，供 agent_service 与 LangGraph HITL 共用。"""


def parse_confirm_intent(text: str) -> str | None:
    """返回 \"confirm\"、\"cancel\" 或无法识别时 None。"""
    raw = text.strip()
    low = raw.lower()
    for w in ("取消", "不录", "不要", "算了", "放弃"):
        if w in raw:
            return "cancel"
    if low in ("n", "no"):
        return "cancel"
    for w in ("确认", "确定", "保存", "录入"):
        if w in raw:
            return "confirm"
    if low in ("ok", "yes", "y"):
        return "confirm"
    if raw in ("好", "行", "嗯", "恩", "可以", "好的", "好吧"):
        return "confirm"
    return None
