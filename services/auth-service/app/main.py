"""Auth service FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.middleware.trace_id import HEADER as TRACE_HEADER
from app.middleware.trace_id import TraceIdMiddleware
from app.routes.auth import router as auth_router
from app.telemetry import setup_telemetry

# FastAPI's status.HTTP_422_UNPROCESSABLE_ENTITY is being renamed; the
# numeric literal sidesteps the deprecation warning across versions.
_HTTP_422 = 422

SERVICE_NAME = "auth-service"

app = FastAPI(title="Maiplot Auth Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)
app.add_middleware(TraceIdMiddleware)
app.include_router(auth_router)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Reshape FastAPI's default 422 into the api-contracts.md envelope."""
    return JSONResponse(
        status_code=_HTTP_422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": {"errors": _safe_errors(exc)},
        },
        headers={TRACE_HEADER: request.headers.get(TRACE_HEADER, "")},
    )


def _safe_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Pydantic v2 puts the raw exception object in ctx['error']; that's not
    JSON serialisable, so strip ctx and stringify any non-primitive input."""
    safe: list[dict[str, object]] = []
    for err in exc.errors():
        safe.append(
            {
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return safe


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
