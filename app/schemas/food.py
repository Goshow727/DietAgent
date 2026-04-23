from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kcal_per_100g: float
    protein_per_100g: float
    carb_per_100g: float
    fat_per_100g: float


class IntakeInlineFood(BaseModel):
    """与食物库中一条记录等价的每 100g 营养，用于照片估计等无 food_id 场景。"""

    name: str = Field(max_length=128)
    kcal_per_100g: float = Field(ge=0)
    protein_per_100g: float = Field(ge=0)
    carb_per_100g: float = Field(ge=0)
    fat_per_100g: float = Field(ge=0)


class IntakeLogCreate(BaseModel):
    food_id: int | None = None
    inline_food: IntakeInlineFood | None = None
    weight_grams: float = Field(gt=0)
    logged_at: datetime | None = None

    @model_validator(mode="after")
    def food_source_xor(self) -> Self:
        has_id = self.food_id is not None
        has_inline = self.inline_food is not None
        if has_id == has_inline:
            raise ValueError("必须且只能提供 food_id 与 inline_food 之一")
        return self


class IntakeLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_name: str
    weight_grams: float
    protein_g: float
    carb_g: float
    fat_g: float
    kcal: float
    logged_at: datetime


class BurnLogCreate(BaseModel):
    exercise_type: str = Field(pattern="^(cardio|anaerobic)$")
    intensity: int = Field(ge=1, le=5)
    duration_minutes: int = Field(gt=0)
    kcal: float = Field(gt=0)
    logged_at: datetime | None = None


class BurnLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_type: str
    intensity: int
    duration_minutes: int
    kcal: float
    logged_at: datetime
