"""Auth service FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.middleware.trace_id import HEADER as TRACE_HEADER
from app.middleware.trace_id import TraceIdMiddleware
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.dev import dev_routes_enabled
from app.routes.dev import router as dev_router
from app.routes.internal import router as internal_router
from app.security import AuthenticationError, AuthorizationError
from app.telemetry import setup_telemetry

# FastAPI's status.HTTP_422_UNPROCESSABLE_ENTITY is being renamed; the
# numeric literal sidesteps the deprecation warning across versions.
_HTTP_422 = 422
_HTTP_401 = 401
_HTTP_403 = 403

SERVICE_NAME = "auth-service"

app = FastAPI(title="Maiplot Auth Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)
app.add_middleware(TraceIdMiddleware)
app.include_router(auth_router)
app.include_router(admin_router)
# Service-to-service only (SCRUM-207). NOT in infra/kong/kong.yml — see the
# module docstring in app/routes/internal.py before touching that.
app.include_router(internal_router)

# Local-only helpers (app/routes/dev.py) — the /dev/otp/latest reader that lets
# a developer complete /auth/otp/verify while the fake SMS adapter is bound.
# This is the PRIMARY security gate: outside ENV=local the routes are never
# registered, so they 404 exactly like any unknown path. See the module
# docstring in app/routes/dev.py for the full set of gates and why each exists.
if dev_routes_enabled(get_settings()):
    app.include_router(dev_router)


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


@app.exception_handler(AuthenticationError)
async def _auth_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Map a failed bearer-token check to a 401 in the standard envelope."""
    return JSONResponse(
        status_code=_HTTP_401,
        content={"error_code": exc.code, "message": exc.message, "details": {}},
        headers={TRACE_HEADER: request.headers.get(TRACE_HEADER, "")},
    )


@app.exception_handler(AuthorizationError)
async def _authz_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    """Map a permission failure (wrong role / non-whitelisted IP) to a 403."""
    return JSONResponse(
        status_code=_HTTP_403,
        content={"error_code": exc.code, "message": exc.message, "details": {}},
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
