"""Listing expiry job (SCRUM-53) — the logic the hourly Celery beat runs.

Two passes, both idempotent:
  * EXPIRE — active listings past expires_at -> status 'expired', re-indexed
    (so they drop out of the feed/search), and an audit_log row recorded.
  * WARN   — active listings within the 48h window that have not yet been
    warned -> an audit_log row + structured log + a seller notification
    (SCRUM-112). The audit row is both the event hook and the re-warn
    idempotency marker, so each listing is warned at most once per cycle.

Kept free of Celery so it can be unit/integration-tested directly; the task
in app/tasks/listing_expiry.py is a thin wrapper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.services.expiry_notifier import ExpiryNotifier, NullExpiryNotifier
from app.services.listing_index_sync import ListingIndexSync

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
        index_sync: ListingIndexSync | None = None,
        warning_window_hours: int = 48,
        notifier: ExpiryNotifier | None = None,
    ) -> None:
        self._listings = listings
        self._audit = audit
        self._index_sync = index_sync
        self._window = warning_window_hours
        self._notifier = notifier or NullExpiryNotifier()

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
            # Sync so the now-expired listing is removed from the search index.
            if self._index_sync is not None:
                await self._index_sync.sync_safe(listing_id)
        return len(ids)

    async def _warn_due(self) -> int:
        targets = await self._listings.list_due_for_expiry_warning(window_hours=self._window)
        for target in targets:
            # Record the audit row FIRST — it's the event hook + the re-warn
            # guard, so a listing is warned at most once per expiry cycle.
            await self._audit.record(
                actor_id=None,
                actor_role="system",
                action="listing.expiry_warning",
                entity_type="listing",
                entity_id=target.listing_id,
                new_value={"window_hours": self._window},
            )
            logger.info(
                "listing.expiry_warning",
                extra={"listing_id": str(target.listing_id), "window_hours": self._window},
            )
            # Notify the seller (SCRUM-112). Best-effort + defensive: a
            # notification failure must never break the expiry job.
            try:
                await self._notifier.expiry_warning(
                    seller_id=target.seller_id, listing_id=target.listing_id
                )
            except Exception as exc:  # noqa: BLE001 — never fail the job
                logger.warning(
                    "listing.expiry_warning.notify_failed",
                    extra={"listing_id": str(target.listing_id), "error": str(exc)},
                )
        return len(targets)
