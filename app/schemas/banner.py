from pydantic import BaseModel, Field


class CardOut(BaseModel):
    id: str
    title: str
    desc: str
    image_url: str | None
    category: str

    model_config = {"from_attributes": True}


class BannerListOut(BaseModel):
    cards: list[CardOut]


class RedCutIn(BaseModel):
    """Optional body: IDs still visible after swipe (excluding the red-cut card)."""

    visible_card_ids: list[str] | None = Field(
        default=None,
        description="Current on-screen ready card ids after removal; used to pick the next card not already shown.",
    )


class RedCutOut(BaseModel):
    card: CardOut | None
