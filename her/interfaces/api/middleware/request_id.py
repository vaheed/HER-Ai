from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request id to each request and response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        state = cast(Any, request.state)
        state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
