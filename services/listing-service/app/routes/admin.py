"""/admin/listings route handlers (admin JWT + IP whitelist gated).

Backend for the listing side of the admin dashboard. Two jobs, deliberately
separate:

  * the **review queue** (SCRUM-24) — pending listings and the approve/reject
    decision that publishes or rejects them; and
  * the **listing console** (SCRUM-215) — browse every listing in any status,
    and open one. The queue answers "what needs deciding"; the console answers
    "show me this property", which nothing could do before.

All endpoints depend on require_admin (admin JWT + IP allowlist, §4).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_admin_listings_service,
    get_admin_queue_service,
    get_listing_review_service,
    require_admin,
)
from app.schemas.listing import (
    AdminListingDetailResponse,
    AdminListingsResponse,
    AdminQueueResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.security import CurrentUser
from app.services.admin_listings import AdminListingsService
from app.services.admin_listings import ListingNotFound as AdminListingNotFound
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


@router.get("", response_model=AdminListingsResponse)
async def browse_listings(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[AdminListingsService, Depends(get_admin_listings_service)],
    search: Annotated[str | None, Query(min_length=2, max_length=300)] = None,
    listing_status: Annotated[str | None, Query(alias="status")] = None,
    authority_type: Annotated[str | None, Query(pattern="^(owner|power_of_attorney)$")] = None,
    state: Annotated[str | None, Query(max_length=100)] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminListingsResponse:
    """Every listing, newest first — the admin's way to FIND a property.

    `status` omitted means every status. `/admin/listings/queue` is the review
    surface and stays pinned to `pending_review`; this is the browse surface, and
    pinning it the same way is what made 13 of 14 listings invisible.

    ⚠️ Declared BEFORE `/{listing_id}` so "queue" and the empty path are not
    swallowed by the UUID route. FastAPI matches in declaration order.
    """
    return await service.browse(
        search=search,
        status=listing_status,
        authority_type=authority_type,
        state=state,
        page=page,
        page_size=page_size,
    )


@router.get("/{listing_id}", response_model=AdminListingDetailResponse)
async def listing_detail(
    listing_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[AdminListingsService, Depends(get_admin_listings_service)],
) -> AdminListingDetailResponse | JSONResponse:
    """One listing in full: the property, its media, the seller block and the
    audit history — the context an approve/reject decision needs and never had.

    Separate from the public `GET /listings/{id}`, which is Redis-cached and
    increments the view counter: an admin reading a listing must not inflate a
    seller's view count or be served a stale body.
    """
    try:
        return await service.detail(listing_id)
    except AdminListingNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
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
