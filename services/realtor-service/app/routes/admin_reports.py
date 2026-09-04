"""/admin/inspections report-review routes (SCRUM-205).

An admin works the queue of submitted inspection reports and approves or
rejects each one. Gated by require_admin (admin JWT + IP allowlist) — the same
reviewers as document review, per the product decision on the ticket.

Reading a report's body is the existing `GET /inspections/{id}/report`, which
already admits `caller.role == "admin"`, so nothing new is needed for a
reviewer to see what they are deciding on.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_report_review_service, require_admin
from app.schemas.report import (
    ReportReviewQueueResponse,
    ReportReviewRequest,
    ReportReviewResponse,
)
from app.security import CurrentUser
from app.services.report_review_service import (
    ReportNotFound,
    ReportNotPending,
    ReportReviewService,
    ReviewNoteRequired,
)

router = APIRouter(prefix="/admin/inspections", tags=["admin-inspection-reports"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ReviewServiceDep = Annotated[ReportReviewService, Depends(get_report_review_service)]

_QUEUE_STATUSES = ("pending", "approved", "rejected")


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/reports/queue", response_model=ReportReviewQueueResponse)
async def report_queue(
    admin: AdminDep,
    service: ReviewServiceDep,
    review_status: Annotated[str, Query(pattern="^(pending|approved|rejected|all)$")] = "pending",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ReportReviewQueueResponse:
    """Submitted reports awaiting a decision, oldest first. `review_status=all`
    returns every submitted report regardless of decision."""
    rows = await service.queue(
        status=None if review_status == "all" else review_status, limit=limit
    )
    return ReportReviewQueueResponse.from_rows(rows)


@router.post("/{inspection_id}/report/review", response_model=None)
async def review_report(
    inspection_id: UUID,
    payload: ReportReviewRequest,
    request: Request,
    admin: AdminDep,
    service: ReviewServiceDep,
) -> ReportReviewResponse | JSONResponse:
    """Approve or reject a submitted report. Rejecting requires a note — it is
    the only thing telling the realtor what to fix."""
    try:
        result = await service.review(
            inspection_id=inspection_id,
            reviewer=admin,
            action=payload.action,
            note=payload.note,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ReportNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "REPORT_NOT_FOUND",
            "No submitted report for that inspection.",
        )
    except ReportNotPending:
        return _error(
            status.HTTP_409_CONFLICT,
            "REPORT_NOT_PENDING",
            "This report has already been reviewed.",
        )
    except ReviewNoteRequired:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "REVIEW_NOTE_REQUIRED",
            "A note is required when rejecting a report.",
        )
    return ReportReviewResponse(
        inspection_id=result.inspection_id,
        report_review_status=result.report_review_status,
    )
