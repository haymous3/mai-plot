"""Document service FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.admin import router as admin_router
from app.routes.documents import router as documents_router
from app.routes.loan_documents import router as loan_documents_router
from app.routes.my_documents import router as my_documents_router
from app.routes.user_documents import router as user_documents_router
from app.routes.view import router as view_router
from app.security import AdminAccessError, AuthenticationError
from app.telemetry import setup_telemetry

# FastAPI's status.HTTP_422_UNPROCESSABLE_ENTITY is being renamed; the
# numeric literal sidesteps the deprecation warning across versions.
_HTTP_422 = 422
_HTTP_403 = 403
_HTTP_401 = 401

SERVICE_NAME = "document-service"

app = FastAPI(title="Maiplot Document Service", version="0.1.0")
setup_telemetry(SERVICE_NAME, app)
app.include_router(documents_router)
app.include_router(loan_documents_router)
app.include_router(my_documents_router)
# Registered BEFORE view_router: `/documents/personal/{id}/view` must not be
# captured by view_router's `/documents/{document_id}/view`, which would parse
# "personal" as a document id.
app.include_router(user_documents_router)
app.include_router(view_router)
app.include_router(admin_router)


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
    )


@app.exception_handler(AuthenticationError)
async def _auth_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Map a failed bearer-token check to a 401 in the standard envelope."""
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
