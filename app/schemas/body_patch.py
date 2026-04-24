from enum import Enum

from pydantic import BaseModel, Field


class BodyMetricsFlow(str, Enum):
    ready = "ready"
    need_clarify = "need_clarify"


class BodyMetricsPatch(BaseModel):
    height: float | None = Field(default=None)
    weight: float | None = Field(default=None)
    age: int | None = Field(default=None)
    gender: str | None = Field(default=None, max_length=16)


class BodyMetricsExtraction(BaseModel):
    flow: BodyMetricsFlow
    clarify_message: str = ""
    patch: BodyMetricsPatch | None = None
