from enum import Enum

from pydantic import BaseModel, Field


class ChatFlow(str, Enum):
    """第二层：摄入结构化（仅在 intent=log_intake 后调用）。"""

    intake_ready = "intake_ready"
    need_clarify = "need_clarify"


class DishKind(str, Enum):
    compound_dish = "compound_dish"
    simple_prep = "simple_prep"
    multi_item = "multi_item"


class AmountSource(str, Enum):
    user_stated = "user_stated"
    estimated = "estimated"
    unknown = "unknown"


class ExtractedFoodItem(BaseModel):
    uttered_name: str = Field(min_length=1, max_length=128)
    dish_kind: DishKind
    lookup_name: str = Field(min_length=1, max_length=128)
    amount_g: float | None = None
    amount_source: AmountSource


class IntakeChatExtraction(BaseModel):
    flow: ChatFlow
    foods: list[ExtractedFoodItem] = Field(default_factory=list)
    clarify_message: str = ""
