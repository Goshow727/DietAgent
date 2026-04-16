from typing import Any, Generic, Optional, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.error_code import ErrorCode, message_of

T = TypeVar("T")


class R(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "ok") -> "R":
        return cls(code=ErrorCode.SUCCESS.value, message=message, data=data)

    @classmethod
    def fail(
        cls,
        code: ErrorCode | int,
        message: str | None = None,
        data: Any = None,
    ) -> "R":
        code_int = int(code)
        return cls(
            code=code_int,
            message=message or message_of(code_int),
            data=data,
        )


def json_response(r: R, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=r.model_dump())
