"""/internal routes — service-to-service calls (SCRUM-207).

Today there is one: issuing a realtor's Maihomme registration number when an
admin approves their application. realtor-service owns that approval; the
number has to live here because LOGIN resolves it (CLAUDE.md §3 — a service
does not read another service's tables).

⚠️ NOT ROUTED THROUGH KONG, and that is load-bearing. `infra/kong/kong.yml`
lists every public path individually and /internal is deliberately absent, so
there is no route from the internet to anything here; auth-service itself is a
private service. Adding /internal to kong.yml would expose an admin-authorised
write with no IP allowlist in front of it — see require_admin in
dependencies.py for the full reasoning.

AUTHENTICATION: the admin's OWN bearer token, forwarded by realtor-service.
The same pattern adapters/deals.py uses in the other direction, and it means no
service-to-service credential had to be invented: the call can do exactly what
the admin who triggered it could do, the audit row names that real admin, and
there is no shared secret to rotate or leak.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_realtor_registration_service, require_admin
from app.schemas.internal import RegistrationNumberResponse
from app.security import CurrentUser
from app.services.realtor_registration import (
    NotRealtorRole,
    RealtorNotFound,
    RealtorRegistrationService,
)

router = APIRouter(prefix="/internal", tags=["internal"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
RegistrationServiceDep = Annotated[
    RealtorRegistrationService, Depends(get_realtor_registration_service)
]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("/realtors/{user_id}/registration-number", response_model=None)
async def issue_registration_number(
    user_id: UUID,
    request: Request,
    admin: AdminDep,
    service: RegistrationServiceDep,
) -> RegistrationNumberResponse | JSONResponse:
    """Issue (or return) the realtor's Maihomme registration number.

    Idempotent: calling it again returns the number already issued and writes no
    second audit row. realtor-service calls this BEFORE it commits an approval,
    so a failure here leaves the realtor pending and retryable rather than
    approved-but-unable-to-sign-in.
    """
    try:
        result = await service.issue(
            user_id=user_id,
            actor=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except RealtorNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such account.")
    except NotRealtorRole:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NOT_REALTOR",
            "A registration number can only be issued to a realtor account.",
        )
    return RegistrationNumberResponse(
        user_id=result.user_id,
        registration_number=result.registration_number,
        newly_issued=result.newly_issued,
    )
