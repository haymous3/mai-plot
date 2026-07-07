"""Unit tests for SellerDealsService (SCRUM-98)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.transaction_repo import SellerDealRow
from app.services.seller_deals import SellerDealsService

pytestmark = pytest.mark.asyncio


class _StubTransactions:
    def __init__(self, rows: list[SellerDealRow]) -> None:
        self._rows = rows
        self.seen: UUID | None = None

    async def list_for_seller(self, seller_id: UUID) -> list[SellerDealRow]:
        self.seen = seller_id
        return self._rows


async def test_maps_and_masks_buyer() -> None:
    buyer = uuid4()
    seller = uuid4()
    row = SellerDealRow(
        id=uuid4(),
        listing_id=uuid4(),
        buyer_id=buyer,
        stage="payment_held",
        agreed_price_kobo=12_000_000_000,
        created_at=datetime.now(UTC),
        property_title="Commercial Land",
        sale_type="normal",
    )
    repo = _StubTransactions([row])
    resp = await SellerDealsService(transactions=repo).list_for_seller(seller)  # type: ignore[arg-type]

    assert repo.seen == seller
    item = resp.data[0]
    assert item.buyer_ref == str(buyer)[:8]
    assert len(item.buyer_ref) == 8
    assert item.stage == "payment_held"
    assert item.property_title == "Commercial Land"


async def test_empty() -> None:
    resp = await SellerDealsService(transactions=_StubTransactions([])).list_for_seller(uuid4())  # type: ignore[arg-type]
    assert resp.data == []
