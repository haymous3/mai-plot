"""Admin listing review (POST /admin/listings/{id}/review).

An admin approves a pending listing (-> active, which makes it visible in the
feed + search) or rejects it (-> rejected, with a required reason). Every
decision is a Listing state change, so it is written to the append-only
audit_log (CLAUDE.md). On a status change the listing is re-indexed so search
reflects the new visibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.security import CurrentUser
from app.services.index_dispatch import IndexDispatcher
from app.services.listing_update import ListingNotFound


class ReviewError(RuntimeError):
    pass


class NotPendingReview(ReviewError):
    """Only a pending_review listing can be reviewed."""


class CommentRequired(ReviewError):
    """A rejection must include a reason."""


@dataclass(frozen=True)
class ReviewResult:
    listing_id: UUID
    status: str


class ListingReviewService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        audit: AuditLogRepository,
        dispatch: IndexDispatcher | None = None,
    ) -> None:
        self._listings = listings
        self._audit = audit
        self._dispatch = dispatch

    async def review(
        self,
        *,
        listing_id: UUID,
        admin: CurrentUser,
        action: str,
        comment: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ReviewResult:
        current = await self._listings.get_owner_status(listing_id)
        if current is None:
            raise ListingNotFound()
        if current.status != "pending_review":
            raise NotPendingReview()

        if action == "reject":
            if not comment or not comment.strip():
                raise CommentRequired()
            new_status, reason = "rejected", comment.strip()
        else:  # approve
            new_status, reason = "active", None

        await self._listings.set_review_status(
            listing_id, new_status=new_status, rejection_reason=reason
        )
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role="admin",
            action=f"listing.{new_status}",
            entity_type="listing",
            entity_id=listing_id,
            old_value={"status": "pending_review"},
            new_value={"status": new_status, "rejection_reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Re-sync so the new visibility is reflected: approve (-> active) indexes
        # it, reject (-> rejected) removes it from the index.
        if self._dispatch is not None:
            await self._dispatch.enqueue(listing_id)
        return ReviewResult(listing_id=listing_id, status=new_status)
