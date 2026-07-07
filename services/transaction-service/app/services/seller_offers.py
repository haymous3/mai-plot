"""Seller "Offers received" inbox (SCRUM-98).

Read-only list of offers on the seller's listings. The per-offer accept/counter/
reject actions live in OfferService (SCRUM-66); this only surfaces the inbox.
Contacts stay masked until acceptance (§8), so the buyer is shown as a short
reference rather than a name.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.offer_repo import OfferRepository
from app.schemas.offer import SellerOfferItem, SellerOffersResponse


class SellerOffersService:
    def __init__(self, *, offers: OfferRepository) -> None:
        self._offers = offers

    async def list_for_seller(self, seller_id: UUID) -> SellerOffersResponse:
        rows = await self._offers.list_for_seller(seller_id)
        return SellerOffersResponse(
            data=[
                SellerOfferItem(
                    id=r.id,
                    listing_id=r.listing_id,
                    property_title=r.property_title,
                    lga=r.lga,
                    state=r.state,
                    buyer_ref=str(r.buyer_id)[:8],
                    offered_price_kobo=r.offered_price_kobo,
                    asking_price_kobo=r.asking_price_kobo,
                    counter_price_kobo=r.counter_price_kobo,
                    note=r.note,
                    status=r.status,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
