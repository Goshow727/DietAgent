from typing_extensions import TypedDict


class DietChatState(TypedDict, total=False):
    """饮食对话图状态（随 Task 6+ 扩展字段）。"""

    user_id: int
    session_id: str
    last_user_text: str
    hitl_phase: str
    reply: str
