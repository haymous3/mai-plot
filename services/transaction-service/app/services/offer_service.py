"""Offer flow orchestration (SCRUM-66).

A buyer makes an offer on a listing; the seller accepts / counters / rejects;
the buyer responds to a counter. Accepting an offer creates a transaction at
the state machine's initial stage ('offer_accepted') and locks the listing
(under_offer). Offer-state transitions are enforced here.

Validations (the ACs): a buyer cannot offer on their own listing; an offer on a
listing that is not 'active' (already under_offer, expired, sold, …) is refused;
offers auto-expire after the configured window (lazily, on the next action).

Seller notification on a new offer is DEFERRED (notification-service is not
built) — a follow-up ticket, like SCRUM-112/113.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.offer_repo import OfferRepository, OfferRow
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser
from app.services.seller_notifier import NullSellerNotifier, SellerNotifier

logger = logging.getLogger(__name__)

# Business rule §4 — the listing is locked to other buyers for 72h once an
# offer is accepted. The window is tracked on transactions.lock_expires_at.
_LISTING_LOCK_SQL = "NOW() + INTERVAL '72 hours'"


class OfferError(RuntimeError):
    pass


class ListingNotFound(OfferError):
    """No live listing with that id."""


class CannotOfferOwnListing(OfferError):
    """A seller cannot make an offer on their own listing."""


class ListingNotAvailable(OfferError):
    """The listing is not 'active' (already under_offer, expired, sold, …)."""


class OfferNotFound(OfferError):
    """No live offer with that id."""


class NotOfferSeller(OfferError):
    """Caller is not the seller this offer was made to."""


class NotOfferBuyer(OfferError):
    """Caller is not the buyer who made this offer."""


class OfferNotActionable(OfferError):
    """The offer is not in a state this action allows."""


class OfferExpired(OfferError):
    """The offer's 72h window elapsed without a response."""


@dataclass(frozen=True)
class AcceptResult:
    offer: OfferRow
    transaction_id: UUID


class OfferService:
    def __init__(
        self,
        *,
        offers: OfferRepository,
        listings: ListingRepository,
        transactions: TransactionRepository,
        audit: AuditLogRepository,
        offer_expiry_hours: int = 72,
        notifier: SellerNotifier | None = None,
    ) -> None:
        self._offers = offers
        self._listings = listings
        self._transactions = transactions
        self._audit = audit
        self._expiry_hours = offer_expiry_hours
        self._notifier = notifier or NullSellerNotifier()

    async def create_offer(
        self, *, buyer: CurrentUser, listing_id: UUID, amount_kobo: int
    ) -> OfferRow:
        listing = await self._listings.get_for_offer(listing_id)
        if listing is None:
            raise ListingNotFound()
        if listing.seller_id == buyer.user_id:
            raise CannotOfferOwnListing()
        now = datetime.now(UTC)
        # A listing under_offer may have a 72h lock that has already lapsed with
        # no progress — reopen it lazily so the new buyer can offer.
        if listing.status == "under_offer" and await self._release_lapsed_lock(listing_id, now):
            listing = await self._listings.get_for_offer(listing_id)
            assert listing is not None
        if listing.status != "active":
            raise ListingNotAvailable()
        if listing.expires_at is not None and listing.expires_at <= now:
            raise ListingNotAvailable()

        offer_id = await self._offers.create(
            listing_id=listing_id,
            buyer_id=buyer.user_id,
            offered_price_kobo=amount_kobo,
            expires_at=now + timedelta(hours=self._expiry_hours),
        )
        logger.info(
            "offer.created", extra={"offer_id": str(offer_id), "listing_id": str(listing_id)}
        )
        # Alert the seller (SCRUM-117) so they can respond in the 72h window.
        # Best-effort + defensive: a notification failure must never block or roll
        # back the offer (the offer is the source of truth).
        try:
            await self._notifier.offer_received(
                seller_id=listing.seller_id,
                offer_id=offer_id,
                listing_id=listing_id,
                amount_kobo=amount_kobo,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, never fail the offer
            logger.warning(
                "offer.notify_failed",
                extra={"offer_id": str(offer_id), "error": str(exc)},
            )
        offer = await self._offers.get(offer_id)
        assert offer is not None
        return offer

    async def accept_offer(self, *, seller: CurrentUser, offer_id: UUID) -> AcceptResult:
        offer = await self._require_offer(offer_id)
        if offer.seller_id != seller.user_id:
            raise NotOfferSeller()
        await self._ensure_actionable(offer, allowed={"pending"})
        return await self._accept(
            offer, accepter=seller.user_id, price_kobo=offer.offered_price_kobo
        )

    async def counter_offer(
        self, *, seller: CurrentUser, offer_id: UUID, counter_amount_kobo: int
    ) -> OfferRow:
        offer = await self._require_offer(offer_id)
        if offer.seller_id != seller.user_id:
            raise NotOfferSeller()
        await self._ensure_actionable(offer, allowed={"pending"})
        await self._offers.set_countered(offer_id, counter_price_kobo=counter_amount_kobo)
        return await self._reload(offer_id)

    async def reject_offer(self, *, seller: CurrentUser, offer_id: UUID) -> OfferRow:
        offer = await self._require_offer(offer_id)
        if offer.seller_id != seller.user_id:
            raise NotOfferSeller()
        await self._ensure_actionable(offer, allowed={"pending"})
        await self._offers.set_status(offer_id, status="rejected")
        return await self._reload(offer_id)

    async def respond_to_counter(
        self, *, buyer: CurrentUser, offer_id: UUID, action: str
    ) -> AcceptResult | OfferRow:
        offer = await self._require_offer(offer_id)
        if offer.buyer_id != buyer.user_id:
            raise NotOfferBuyer()
        await self._ensure_actionable(offer, allowed={"countered"})
        if action == "accept":
            assert offer.counter_price_kobo is not None
            return await self._accept(
                offer, accepter=buyer.user_id, price_kobo=offer.counter_price_kobo
            )
        await self._offers.set_status(offer_id, status="rejected")
        return await self._reload(offer_id)

    # -- internals ---------------------------------------------------------

    async def _release_lapsed_lock(self, listing_id: UUID, now: datetime) -> bool:
        """If a listing is under_offer but its 72h lock has lapsed with the deal
        still parked at offer_accepted, cancel that abandoned transaction and
        reopen the listing. Returns True if it released. A deal that has
        progressed past offer_accepted is a live deal and stays locked.

        This is the lazy path (mirrors the lazy offer-expiry pattern); a Celery
        sweep that reopens lapsed locks off-request is the proactive follow-up.
        """
        lock = await self._transactions.get_lock_for_listing(listing_id)
        if lock is None or lock.stage != "offer_accepted":
            return False
        if lock.lock_expires_at is None or lock.lock_expires_at > now:
            return False  # lock still live
        await self._transactions.update_stage(lock.transaction_id, stage="cancelled")
        await self._transactions.append_event(
            transaction_id=lock.transaction_id,
            event_type="lock_expired",
            from_stage="offer_accepted",
            to_stage="cancelled",
            triggered_by=None,
            metadata={"reason": "listing_lock_expired"},
        )
        await self._audit.record(
            actor_id=None,
            actor_role="system",
            action="transaction.cancelled",
            entity_type="transaction",
            entity_id=lock.transaction_id,
            old_value={"stage": "offer_accepted"},
            new_value={"stage": "cancelled", "reason": "listing_lock_expired"},
        )
        await self._listings.release_lock(listing_id)
        logger.info(
            "listing.lock_released",
            extra={
                "listing_id": str(listing_id),
                "transaction_id": str(lock.transaction_id),
            },
        )
        return True

    async def _accept(self, offer: OfferRow, *, accepter: UUID, price_kobo: int) -> AcceptResult:
        # Re-check the listing is still available so two offers can't both be
        # accepted into two transactions for one listing.
        listing = await self._listings.get_for_offer(offer.listing_id)
        if listing is None or listing.status != "active":
            raise ListingNotAvailable()

        transaction_id = await self._transactions.create_at_offer_accepted(
            listing_id=offer.listing_id,
            buyer_id=offer.buyer_id,
            seller_id=offer.seller_id,
            agreed_price_kobo=price_kobo,
            lock_expires_at_sql=_LISTING_LOCK_SQL,
        )
        await self._transactions.append_event(
            transaction_id=transaction_id,
            event_type="offer_accepted",
            to_stage="offer_accepted",
            triggered_by=accepter,
            metadata={"offer_id": str(offer.id), "agreed_price_kobo": price_kobo},
        )
        await self._offers.set_accepted(offer.id)
        await self._listings.mark_under_offer(offer.listing_id)
        logger.info(
            "offer.accepted",
            extra={"offer_id": str(offer.id), "transaction_id": str(transaction_id)},
        )
        return AcceptResult(offer=await self._reload(offer.id), transaction_id=transaction_id)

    async def _require_offer(self, offer_id: UUID) -> OfferRow:
        offer = await self._offers.get(offer_id)
        if offer is None:
            raise OfferNotFound()
        return offer

    async def _reload(self, offer_id: UUID) -> OfferRow:
        offer = await self._offers.get(offer_id)
        assert offer is not None
        return offer

    async def _ensure_actionable(self, offer: OfferRow, *, allowed: set[str]) -> None:
        """Lazy 72h expiry + state guard. An offer past its window is refused
        (logically expired). The status is NOT mutated — the offers table's CHECK
        has no 'expired' value; a Celery sweep + schema change is the follow-up."""
        if offer.status in ("pending", "countered") and offer.expires_at <= datetime.now(UTC):
            raise OfferExpired()
        if offer.status not in allowed:
            raise OfferNotActionable()
