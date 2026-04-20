from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BurnLog(Base, TimestampMixin):
    __tablename__ = "burn_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    exercise_type: Mapped[str] = mapped_column(String(32), nullable=False)
    intensity: Mapped[int]
    duration_minutes: Mapped[int]
    kcal: Mapped[float]
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
