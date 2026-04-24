from typing_extensions import TypedDict


class DietChatState(TypedDict, total=False):
    """LangGraph 饮食对话状态（由 MemorySaver/Redis 等 checkpoint 持久化）。"""

    user_id: int
    session_id: str
    last_user_text: str
    hitl_phase: str  # idle | awaiting_confirm
    pending_confirm_kind: str  # none | intake | burn | body | preference
    routed_intent: str
    intake_pending_context: str | None
    burn_pending_context: str | None
    intake_draft_lines: list[dict]
    burn_draft_lines: list[dict]
    body_patch_dict: dict
    preference_items: list[dict]
    reply: str
