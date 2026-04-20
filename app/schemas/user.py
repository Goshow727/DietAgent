from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    email: str | None = Field(default=None, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    is_active: bool
    created_at: datetime
    nickname: str | None = None
    avatar_url: str | None = None
    height: float | None = None
    weight: float | None = None
    age: int | None = None
    gender: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=64)
    height: float | None = None
    weight: float | None = None
    age: int | None = None
    gender: str | None = Field(default=None, pattern="^(male|female|other)$")


class AccountStatusOut(BaseModel):
    is_active: bool
