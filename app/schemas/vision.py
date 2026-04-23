from typing import Self

from pydantic import BaseModel, Field, model_validator


class IntakeEstimatePayload(BaseModel):
    name: str
    kcal_per_100g: float = Field(ge=0)
    protein_per_100g: float = Field(ge=0)
    carb_per_100g: float = Field(ge=0)
    fat_per_100g: float = Field(ge=0)
    suggested_food_id: int | None = None


class BurnEstimatePayload(BaseModel):
    exercise_type: str = Field(pattern="^(cardio|anaerobic)$")
    intensity: int = Field(ge=1, le=5)
    duration_minutes: int = Field(gt=0)
    kcal: float = Field(gt=0)


class AnalyzePhotoData(BaseModel):
    result_type: str = Field(pattern="^(intake|burn|uncertain)$")
    intake: IntakeEstimatePayload | None = Field(default=None)
    burn: BurnEstimatePayload | None = Field(default=None)
    message: str | None = None

    @model_validator(mode="after")
    def payload_matches_type(self) -> Self:
        if self.result_type == "intake" and self.intake is None:
            raise ValueError("intake payload required when result_type is intake")
        if self.result_type == "burn" and self.burn is None:
            raise ValueError("burn payload required when result_type is burn")
        return self
