from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class InsightTag(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    tabTemp: int = Field(ge=0, le=2)


class HomeInsightPeriod(BaseModel):
    period_start: date
    period_end: date
    label_hint: str | None = None


class HomeInsightData(BaseModel):
    insight_type: Literal["month", "week", "daily"]
    period: HomeInsightPeriod
    desc: str
    tags: list[InsightTag]
