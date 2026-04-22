from pydantic import BaseModel, Field


class IntakeDraftLine(BaseModel):
    lookup_name: str
    uttered_name: str
    amount_g: float = Field(gt=0)


class IntakeConfirmDraft(BaseModel):
    items: list[IntakeDraftLine]
