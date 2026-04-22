from enum import Enum

from pydantic import BaseModel, Field


class BurnFlow(str, Enum):
    burn_ready = "burn_ready"
    need_clarify = "need_clarify"


class BurnMetricSource(str, Enum):
    user_stated = "user_stated"
    estimated = "estimated"
    unknown = "unknown"


class BurnExtractedItem(BaseModel):
    exercise_type: str = Field(pattern="^(cardio|anaerobic)$")
    intensity: int = Field(ge=1, le=5)
    duration_minutes: int | None = None
    kcal: float | None = None
    duration_source: BurnMetricSource
    kcal_source: BurnMetricSource
    activity_note: str = ""


class BurnChatExtraction(BaseModel):
    flow: BurnFlow
    items: list[BurnExtractedItem] = Field(default_factory=list)
    clarify_message: str = ""
