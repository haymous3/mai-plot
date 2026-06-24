"""/admin/realtors routes — credential review (SCRUM-71).

The admin/legal team reviews pending realtor applications: approve, reject (with
reason), or suspend an approved realtor. Gated by require_admin (admin JWT + IP
allowlist).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_realtor_repo, get_review_service, require_admin
from app.repositories.realtor_repo import RealtorRepository
from app.schemas.realtor import (
    RealtorQueueItem,
    RealtorQueueResponse,
    RealtorReviewRequest,
    RealtorReviewResponse,
)
from app.security import CurrentUser
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
) -> RealtorReviewResponse | JSONResponse:
    """Approve / reject / suspend a realtor. Reject + suspend require a reason."""
    try:
        result = await service.review(
            user_id=user_id,
            reviewer=admin,
            action=payload.action,
            reason=payload.reason,
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
    return RealtorReviewResponse(id=result.user_id, approval_status=result.approval_status)
