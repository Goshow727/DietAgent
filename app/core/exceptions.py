from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_code import ErrorCode, message_of
from app.core.response import R, json_response


class BusinessException(Exception):
    def __init__(
        self,
        code: ErrorCode | int,
        message: str | None = None,
        data: object | None = None,
    ) -> None:
        self.code = int(code)
        self.message = message or message_of(self.code)
        self.data = data
        super().__init__(self.message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessException)
    async def _handle_business(_, exc: BusinessException):
        logger.warning(f"[business] code={exc.code} msg={exc.message}")
        return json_response(R.fail(exc.code, exc.message, exc.data))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            details.append(f"{loc}: {err.get('msg')}")
        message = "; ".join(details) or "参数错误"
        logger.warning(f"[validation] {message}")
        return json_response(R.fail(ErrorCode.PARAM_INVALID, message))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_, exc: StarletteHTTPException):
        code_map = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.METHOD_NOT_ALLOWED,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return json_response(R.fail(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _handle_unknown(_, exc: Exception):
        logger.exception(f"[unhandled] {exc}")
        return json_response(R.fail(ErrorCode.INTERNAL_ERROR))
