"""Transaction service FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.escrow import router as escrow_router
from app.routes.payments import router as payments_router
from app.routes.transactions import router as transactions_router
from app.routes.webhooks import router as webhooks_router
from app.security import AdminAccessError, AuthenticationError
from app.telemetry import setup_telemetry

_HTTP_422 = 422
_HTTP_401 = 401
_HTTP_403 = 403

SERVICE_NAME = "transaction-service"

app = FastAPI(title="Maiplot Transaction Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)
app.include_router(transactions_router)
app.include_router(escrow_router)
app.include_router(payments_router)
app.include_router(webhooks_router)


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


@app.exception_handler(AdminAccessError)
async def _admin_handler(request: Request, exc: AdminAccessError) -> JSONResponse:
    """Map a failed admin gate (role / IP) to a 403 in the standard envelope."""
    return JSONResponse(
        status_code=_HTTP_403,
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
