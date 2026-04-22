from typing import Literal

from pydantic import BaseModel, Field


class BurnDraftLine(BaseModel):
    exercise_type: Literal["cardio", "anaerobic"]
    intensity: int = Field(ge=1, le=5)
    duration_minutes: int = Field(gt=0)
    kcal: float = Field(gt=0)
    activity_note: str = ""


class BurnConfirmDraft(BaseModel):
    items: list[BurnDraftLine]
