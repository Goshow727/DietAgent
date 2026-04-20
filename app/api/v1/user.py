from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import CurrentUser, CurrentUserRaw, DbSession
from app.core.response import R
from app.schemas.user import AccountStatusOut, UserRead, UserUpdate
from app.services import oss_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=R[UserRead])
async def get_user(current: CurrentUser) -> R[UserRead]:
    return R.ok(UserRead.model_validate(current))


@router.put("", response_model=R[UserRead])
async def update_user(
    db: DbSession,
    current: CurrentUser,
    nickname: str | None = Form(default=None),
    height: float | None = Form(default=None),
    weight: float | None = Form(default=None),
    age: int | None = Form(default=None),
    gender: str | None = Form(default=None),
    avatar: UploadFile | None = File(default=None),
) -> R[UserRead]:
    avatar_url: str | None = None
    if avatar is not None:
        data = await avatar.read()
        avatar_url = oss_service.upload_avatar(data, avatar.content_type or "image/jpeg")

    payload = UserUpdate(nickname=nickname, height=height, weight=weight, age=age, gender=gender)
    user = await user_service.update_user(db, current, payload, avatar_url)
    return R.ok(UserRead.model_validate(user))


@router.get("/status", response_model=R[AccountStatusOut])
async def account_status(current: CurrentUserRaw) -> R[AccountStatusOut]:
    return R.ok(AccountStatusOut(is_active=current.is_active))
