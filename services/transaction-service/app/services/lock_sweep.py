"""Proactive sweep of lapsed 72h listing locks (SCRUM-149).

Business rule §4: accepting an offer locks the listing to other buyers for 72h
(tracked on transactions.lock_expires_at). OfferService releases a lapsed lock
LAZILY — only when a new buyer tries to offer on that listing. This beat sweep
is the proactive counterpart: it finds every transaction still parked at
'offer_accepted' past its lock window and cancels it, reopening the listing so
it resurfaces in the feed even if no one offers again.

The per-lock steps mirror OfferService._release_lapsed_lock exactly (cancel the
abandoned transaction → append a 'lock_expired' event → audit → release the
listing). Idempotent + re-entrant: the repo query only returns still-locked
'offer_accepted' deals, so a deal cancelled on one pass is gone the next.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)

_REASON = "listing_lock_expired"


@dataclass(frozen=True)
class LockSweepResult:
    scanned: int
    released: int


class ListingLockSweepService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        listings: ListingRepository,
        audit: AuditLogRepository,
        batch_limit: int = 500,
    ) -> None:
        self._transactions = transactions
        self._listings = listings
        self._audit = audit
        self._batch_limit = batch_limit

    async def run(self) -> LockSweepResult:
        lapsed = await self._transactions.list_lapsed_locks(limit=self._batch_limit)
        for lock in lapsed:
            await self._transactions.update_stage(lock.transaction_id, stage="cancelled")
            await self._transactions.append_event(
                transaction_id=lock.transaction_id,
                event_type="lock_expired",
                from_stage="offer_accepted",
                to_stage="cancelled",
                triggered_by=None,
                metadata={"reason": _REASON},
            )
            await self._audit.record(
                actor_id=None,
                actor_role="system",
                action="transaction.cancelled",
                entity_type="transaction",
                entity_id=lock.transaction_id,
                old_value={"stage": "offer_accepted"},
                new_value={"stage": "cancelled", "reason": _REASON},
            )
            await self._listings.release_lock(lock.listing_id)
        if lapsed:
            logger.info("listing.lock_sweep.released", extra={"count": len(lapsed)})
        return LockSweepResult(scanned=len(lapsed), released=len(lapsed))
