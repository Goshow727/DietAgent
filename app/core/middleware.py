import uuid
from typing import Awaitable, Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACE_HEADER = "X-Trace-Id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or uuid.uuid4().hex[:16]
        request.state.trace_id = trace_id
        with logger.contextualize(trace_id=trace_id):
            logger.info(f"--> {request.method} {request.url.path}")
            response = await call_next(request)
            logger.info(f"<-- {request.method} {request.url.path} {response.status_code}")
        response.headers[TRACE_HEADER] = trace_id
        return response
