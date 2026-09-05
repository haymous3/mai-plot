"""/admin/realtors routes — credential review (SCRUM-71).

The admin/legal team reviews pending realtor applications: approve, reject (with
reason), or suspend an approved realtor. Gated by require_admin (admin JWT + IP
allowlist).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.adapters.registration_number import RegistrationNumberUnavailable
from app.dependencies import (
    get_credential_service,
    get_realtor_repo,
    get_review_service,
    require_admin,
)
from app.repositories.realtor_repo import RealtorRepository
from app.schemas.realtor import (
    GovernmentIdUrlResponse,
    RealtorQueueItem,
    RealtorQueueResponse,
    RealtorReviewRequest,
    RealtorReviewResponse,
)
from app.security import CurrentUser, parse_bearer
from app.services.credential_service import CredentialAccessService, CredentialUnavailable
from app.services.realtor_review import (
    RealtorNotActionable,
    RealtorNotFound,
    RealtorReviewService,
    ReasonRequired,
)

router = APIRouter(prefix="/admin/realtors", tags=["admin-realtors"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ReviewServiceDep = Annotated[RealtorReviewService, Depends(get_review_service)]
RealtorRepoDep = Annotated[RealtorRepository, Depends(get_realtor_repo)]
CredentialServiceDep = Annotated[CredentialAccessService, Depends(get_credential_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/queue", response_model=RealtorQueueResponse)
async def review_queue(admin: AdminDep, realtors: RealtorRepoDep) -> RealtorQueueResponse:
    """Pending realtor applications, oldest first."""
    rows = await realtors.list_pending()
    return RealtorQueueResponse(items=[RealtorQueueItem.from_row(r) for r in rows])


@router.post("/{user_id}/review", response_model=None)
async def review_realtor(
    user_id: UUID,
    payload: RealtorReviewRequest,
    request: Request,
    admin: AdminDep,
    service: ReviewServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> RealtorReviewResponse | JSONResponse:
    """Approve / reject / suspend a realtor. Reject + suspend require a reason.

    An approval also issues the realtor's Maihomme registration number from
    auth-service (SCRUM-207), which is why the admin's own bearer token is
    forwarded: the issuance endpoint authorises on that token rather than on a
    service credential. AdminDep has already validated the header by the time
    parse_bearer sees it, so it cannot fail here for a request that got this far.
    """
    try:
        result = await service.review(
            user_id=user_id,
            reviewer=admin,
            action=payload.action,
            reason=payload.reason,
            reviewer_token=parse_bearer(authorization),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except RealtorNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "REALTOR_NOT_FOUND", "No such realtor.")
    except RealtorNotActionable:
        return _error(
            status.HTTP_409_CONFLICT,
            "REALTOR_NOT_ACTIONABLE",
            "The realtor is not in a state this action allows.",
        )
    except ReasonRequired:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "REASON_REQUIRED",
            "A reason is required to reject or suspend.",
        )
    except RegistrationNumberUnavailable:
        # Fail closed (SCRUM-207): the approval is NOT committed. An approved
        # realtor with no registration number cannot sign in by number (there
        # isn't one) or by email (refused because they are approved), and no admin
        # action reaches that state. Retrying is safe — issuance is idempotent.
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "REGISTRATION_NUMBER_UNAVAILABLE",
            "We could not issue this realtor's registration number. Please try again shortly.",
        )
    return RealtorReviewResponse(
        id=result.user_id,
        approval_status=result.approval_status,
        registration_number=result.registration_number,
    )


@router.get("/{user_id}/government-id", response_model=None)
async def government_id(
    user_id: UUID,
    request: Request,
    admin: AdminDep,
    service: CredentialServiceDep,
) -> GovernmentIdUrlResponse | JSONResponse:
    """A short-TTL pre-signed URL for the realtor's uploaded ID document, so the
    reviewer can view the credential. Access is recorded in audit_log."""
    try:
        url = await service.government_id_url(
            user_id=user_id,
            viewer=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except RealtorNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "REALTOR_NOT_FOUND", "No such realtor.")
    except CredentialUnavailable:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "CREDENTIAL_UNAVAILABLE",
            "This realtor has no ID document on file.",
        )
    return GovernmentIdUrlResponse(url=url)
