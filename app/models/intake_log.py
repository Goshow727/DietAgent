from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class IntakeLog(Base, TimestampMixin):
    __tablename__ = "intake_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), nullable=False)
    food_name: Mapped[str] = mapped_column(String(128), nullable=False)
    weight_grams: Mapped[float]
    protein_g: Mapped[float]
    carb_g: Mapped[float]
    fat_g: Mapped[float]
    kcal: Mapped[float]
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
