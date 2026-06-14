"""Listing expiry job (SCRUM-53) — the logic the hourly Celery beat runs.

Two passes, both idempotent:
  * EXPIRE — active listings past expires_at -> status 'expired', re-indexed
    (so they drop out of the feed/search), and an audit_log row recorded.
  * WARN   — active listings within the 48h window that have not yet been
    warned -> an audit_log row + structured log. The actual seller
    notification send is DEFERRED to notification-service (not built yet);
    the audit row is both the event hook and the re-warn idempotency marker.

Kept free of Celery so it can be unit/integration-tested directly; the task
in app/tasks/listing_expiry.py is a thin wrapper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.services.listing_indexer import ListingIndexer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpiryResult:
    expired: int
    warned: int


class ListingExpiryService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        audit: AuditLogRepository,
        indexer: ListingIndexer | None = None,
        warning_window_hours: int = 48,
    ) -> None:
        self._listings = listings
        self._audit = audit
        self._indexer = indexer
        self._window = warning_window_hours

    async def run(self) -> ExpiryResult:
        expired = await self._expire_due()
        warned = await self._warn_due()
        logger.info("listing.expiry.run", extra={"expired": expired, "warned": warned})
        return ExpiryResult(expired=expired, warned=warned)

    async def _expire_due(self) -> int:
        ids = await self._listings.list_active_expired()
        for listing_id in ids:
            await self._listings.mark_expired(listing_id)
            await self._audit.record(
                actor_id=None,
                actor_role="system",
                action="listing.expired",
                entity_type="listing",
                entity_id=listing_id,
                old_value={"status": "active"},
                new_value={"status": "expired"},
            )
            # Re-index so the expired listing leaves the feed/search.
            if self._indexer is not None:
                await self._indexer.reindex_safe(listing_id)
        return len(ids)

    async def _warn_due(self) -> int:
        ids = await self._listings.list_due_for_expiry_warning(window_hours=self._window)
        for listing_id in ids:
            # The audit row is the event hook + the re-warn guard. The actual
            # Web Push/SMS send is wired when notification-service lands.
            await self._audit.record(
                actor_id=None,
                actor_role="system",
                action="listing.expiry_warning",
                entity_type="listing",
                entity_id=listing_id,
                new_value={"window_hours": self._window},
            )
            logger.info(
                "listing.expiry_warning",
                extra={"listing_id": str(listing_id), "window_hours": self._window},
            )
        return len(ids)
