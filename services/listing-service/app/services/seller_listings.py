"""Seller "My Listings" — list own listings + pause/resume (SCRUM-98).

Non-§11. Pause/resume only toggles a listing's visibility (active <-> paused);
only the owner may act, and only on a listing in the right state.

⚠️ **Both toggles MUST re-index (fixed in SCRUM-215).** `paused` is not in
`INDEXABLE_STATUSES`, but this service was built without an `IndexDispatcher`,
so pausing changed the row and left the Elasticsearch document alone — still
carrying `status: "active"`, which is the exact term the search query filters
on. A paused listing therefore stayed findable in search indefinitely. The feed
was unaffected (it reads the DB), which is why it went unnoticed: the listing
vanished from the homepage and stayed in the search results.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.listing_repo import ListingRepository
from app.schemas.listing import SellerListingItem, SellerListingsResponse
from app.security import CurrentUser
from app.services.index_dispatch import IndexDispatcher


class SellerListingError(RuntimeError):
    pass


class ListingNotFound(SellerListingError):
    pass


class NotListingOwner(SellerListingError):
    pass


class ListingNotPausable(SellerListingError):
    """The listing isn't in a state that can be paused/resumed."""


class SellerListingsService:
    def __init__(
        self, *, listings: ListingRepository, dispatch: IndexDispatcher | None = None
    ) -> None:
        self._listings = listings
        self._dispatch = dispatch

    async def list_mine(self, seller_id: UUID) -> SellerListingsResponse:
        rows = await self._listings.list_for_seller(seller_id)
        return SellerListingsResponse(
            data=[
                SellerListingItem(
                    id=r.id,
                    title=r.title,
                    property_type=r.property_type,
                    state=r.state,
                    lga=r.lga,
                    size_sqm=r.size_sqm,
                    asking_price_kobo=r.asking_price_kobo,
                    sale_type=r.sale_type,
                    status=r.status,
                    doc_verification_status=r.doc_verification_status,
                    view_count=r.view_count,
                    offers_count=r.offers_count,
                    saves_count=r.saves_count,
                    urgency_expires_at=r.urgency_expires_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )

    async def _authorise(self, listing_id: UUID, caller: CurrentUser) -> str:
        owner = await self._listings.get_owner_status(listing_id)
        if owner is None:
            raise ListingNotFound
        if owner.seller_id != caller.user_id:
            raise NotListingOwner
        return owner.status

    async def pause(self, *, listing_id: UUID, caller: CurrentUser) -> None:
        status = await self._authorise(listing_id, caller)
        if status != "active":
            raise ListingNotPausable
        await self._listings.set_status(listing_id, status="paused")
        await self._reindex(listing_id)

    async def resume(self, *, listing_id: UUID, caller: CurrentUser) -> None:
        status = await self._authorise(listing_id, caller)
        if status != "paused":
            raise ListingNotPausable
        await self._listings.set_status(listing_id, status="active")
        await self._reindex(listing_id)

    async def _reindex(self, listing_id: UUID) -> None:
        """Reconcile the search document with the new visibility. Best-effort by
        construction — the dispatcher swallows transport failures — so a broker
        hiccup leaves a stale document for the reconcile sweep rather than
        failing a toggle the seller already saw succeed."""
        if self._dispatch is not None:
            await self._dispatch.enqueue(listing_id)
