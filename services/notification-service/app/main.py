"""Notification service FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.notifications import router as notifications_router
from app.routes.preferences import router as preferences_router
from app.routes.push import router as push_router
from app.security import AuthenticationError
from app.telemetry import setup_telemetry

_HTTP_422 = 422
_HTTP_401 = 401

SERVICE_NAME = "notification-service"

app = FastAPI(title="Maiplot Notification Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)
app.include_router(notifications_router)
app.include_router(push_router)
app.include_router(preferences_router)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=_HTTP_422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": {"errors": _safe_errors(exc)},
        },
    )


@app.exception_handler(AuthenticationError)
async def _auth_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=_HTTP_401,
        content={"error_code": exc.code, "message": exc.message, "details": {}},
    )


def _safe_errors(exc: RequestValidationError) -> list[dict[str, object]]:
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
