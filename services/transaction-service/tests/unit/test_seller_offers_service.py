"""Unit tests for SellerOffersService (SCRUM-98)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.offer_repo import SellerOfferRow
from app.services.seller_offers import SellerOffersService

pytestmark = pytest.mark.asyncio


class _StubOffers:
    def __init__(self, rows: list[SellerOfferRow]) -> None:
        self._rows = rows
        self.seen: UUID | None = None

    async def list_for_seller(self, seller_id: UUID) -> list[SellerOfferRow]:
        self.seen = seller_id
        return self._rows


def _row(buyer_id: UUID, *, note: str | None = None) -> SellerOfferRow:
    return SellerOfferRow(
        id=uuid4(),
        listing_id=uuid4(),
        buyer_id=buyer_id,
        property_title="2 Plots of Land",
        lga="Eti-Osa",
        state="Lagos",
        asking_price_kobo=4_500_000_000,
        offered_price_kobo=4_200_000_000,
        counter_price_kobo=None,
        note=note,
        status="pending",
        created_at=datetime.now(UTC),
    )


async def test_maps_and_masks_buyer() -> None:
    buyer = uuid4()
    seller = uuid4()
    repo = _StubOffers([_row(buyer, note="Interested for development.")])
    resp = await SellerOffersService(offers=repo).list_for_seller(seller)  # type: ignore[arg-type]

    assert repo.seen == seller
    item = resp.data[0]
    # Buyer surfaced only as a short reference — not the full id.
    assert item.buyer_ref == str(buyer)[:8]
    assert len(item.buyer_ref) == 8
    assert item.note == "Interested for development."
    assert item.asking_price_kobo == 4_500_000_000
    assert item.offered_price_kobo == 4_200_000_000


async def test_empty_list() -> None:
    resp = await SellerOffersService(offers=_StubOffers([])).list_for_seller(uuid4())  # type: ignore[arg-type]
    assert resp.data == []
