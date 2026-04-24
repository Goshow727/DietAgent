from enum import Enum

from pydantic import BaseModel, Field


class PreferenceFlow(str, Enum):
    ready = "ready"
    need_clarify = "need_clarify"


class PreferenceItem(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    raw_text: str = Field(min_length=1, max_length=512)


class PreferenceExtraction(BaseModel):
    flow: PreferenceFlow
    clarify_message: str = ""
    items: list[PreferenceItem] = Field(default_factory=list)


class PreferenceConfirmDraft(BaseModel):
    """待用户确认写入的偏好列表（Redis / HITL 草案）。"""

    items: list[PreferenceItem] = Field(default_factory=list)
