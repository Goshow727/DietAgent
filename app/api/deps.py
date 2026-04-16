from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.user_service import get_user_by_id

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise BusinessException(ErrorCode.UNAUTHORIZED, "缺少 Authorization 头")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise BusinessException(ErrorCode.UNAUTHORIZED, "Authorization 格式错误")
    return parts[1]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    token = _extract_token(authorization)
    payload = decode_token(token)
    sub = payload.get("sub")
    if not sub:
        raise BusinessException(ErrorCode.TOKEN_INVALID)
    user = await get_user_by_id(db, int(sub))
    if not user:
        raise BusinessException(ErrorCode.USER_NOT_FOUND)
    if not user.is_active:
        raise BusinessException(ErrorCode.FORBIDDEN, "用户已被禁用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
