from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    kcal_per_100g: Mapped[float]
    protein_per_100g: Mapped[float]
    carb_per_100g: Mapped[float]
    fat_per_100g: Mapped[float]
