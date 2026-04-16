from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.response import R
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=R[UserRead])
async def me(current: CurrentUser) -> R[UserRead]:
    return R.ok(UserRead.model_validate(current))
