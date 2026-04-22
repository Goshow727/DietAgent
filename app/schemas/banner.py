from pydantic import BaseModel


class CardOut(BaseModel):
    id: str
    title: str
    desc: str
    image_url: str | None
    category: str

    model_config = {"from_attributes": True}


class BannerListOut(BaseModel):
    cards: list[CardOut]


class RedCutOut(BaseModel):
    card: CardOut | None
