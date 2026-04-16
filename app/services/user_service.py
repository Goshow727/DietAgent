from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import TokenOut, UserCreate, UserLogin


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def register_user(db: AsyncSession, payload: UserCreate) -> User:
    exists = await get_user_by_username(db, payload.username)
    if exists:
        raise BusinessException(ErrorCode.USER_ALREADY_EXISTS)

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, payload: UserLogin) -> TokenOut:
    user = await get_user_by_username(db, payload.username)
    if not user:
        raise BusinessException(ErrorCode.USER_NOT_FOUND)
    if not verify_password(payload.password, user.hashed_password):
        raise BusinessException(ErrorCode.PASSWORD_INCORRECT)

    token = create_access_token(subject=user.id, extra={"username": user.username})
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
