from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kcal_per_100g: float
    protein_per_100g: float
    carb_per_100g: float
    fat_per_100g: float


class IntakeLogCreate(BaseModel):
    food_id: int
    weight_grams: float = Field(gt=0)
    logged_at: datetime | None = None


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
