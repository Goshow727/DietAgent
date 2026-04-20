from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.response import R
from app.schemas.user import TokenOut, UserCreate, UserLogin, UserRead
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=R[UserRead])
async def register(payload: UserCreate, db: DbSession) -> R[UserRead]:
    user = await user_service.register_user(db, payload)
    return R.ok(UserRead.model_validate(user))


@router.post("/login", response_model=R[TokenOut])
async def login(payload: UserLogin, db: DbSession) -> R[TokenOut]:
    result = await user_service.login_user(db, payload)
    return R.ok(result)
