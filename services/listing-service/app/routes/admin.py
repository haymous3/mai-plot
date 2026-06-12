"""/admin/listings route handlers (admin JWT + IP whitelist gated).

Backend for the listing-review part of the admin dashboard (SCRUM-24): the
queue of pending listings and the approve/reject decision that activates or
rejects them. All endpoints depend on require_admin.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_admin_queue_service,
    get_listing_review_service,
    require_admin,
)
from app.schemas.listing import (
    AdminQueueResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.security import CurrentUser
from app.services.admin_queue import AdminQueueService
from app.services.listing_review import (
    CommentRequired,
    ListingReviewService,
    NotPendingReview,
)
from app.services.listing_update import ListingNotFound

router = APIRouter(prefix="/admin/listings", tags=["admin"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/queue", response_model=AdminQueueResponse)
async def review_queue(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[AdminQueueService, Depends(get_admin_queue_service)],
    listing_status: Annotated[str, Query(alias="status")] = "pending_review",
    authority_type: str | None = Query(default=None, pattern="^(owner|power_of_attorney)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminQueueResponse:
    return await service.list_queue(
        status=listing_status,
        authority_type=authority_type,
        page=page,
        page_size=page_size,
    )


@router.post("/{listing_id}/review", response_model=ReviewResponse)
async def review_listing(
    listing_id: UUID,
    body: ReviewRequest,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[ListingReviewService, Depends(get_listing_review_service)],
) -> ReviewResponse | JSONResponse:
    try:
        result = await service.review(
            listing_id=listing_id,
            admin=admin,
            action=body.action,
            comment=body.comment,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ListingNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
        )
    except NotPendingReview:
        return _error(
            422,
            "LISTING_NOT_PENDING_REVIEW",
            "Only a listing awaiting review can be approved or rejected.",
        )
    except CommentRequired:
        return _error(422, "COMMENT_REQUIRED_FOR_REJECTION", "A rejection must include a comment.")

    return ReviewResponse(listing_id=result.listing_id, status=result.status)
