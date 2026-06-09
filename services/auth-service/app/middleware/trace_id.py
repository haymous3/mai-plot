"""Trace ID middleware — review.md O1.

Reads `X-Trace-ID` from the incoming request, validates it as UUID v4,
or generates a fresh one. Binds it to structlog contextvars so every
log line in the request chain carries it. Echoes the value back on the
response so clients can correlate.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

HEADER = "X-Trace-ID"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = _coerce_trace_id(request.headers.get(HEADER))
        # contextvars binding propagates to every structlog call further
        # down the request chain.
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")
        response.headers[HEADER] = trace_id
        return response


def _coerce_trace_id(raw: str | None) -> str:
    if raw:
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            pass
    return str(uuid.uuid4())
