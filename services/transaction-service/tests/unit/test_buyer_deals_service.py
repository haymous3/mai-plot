"""Unit tests for BuyerDealsService (SCRUM-95)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.transaction_repo import DealRow
from app.services.buyer_deals import BuyerDealsService

pytestmark = pytest.mark.asyncio


def _row(title: str, stage: str) -> DealRow:
    return DealRow(
        id=uuid4(),
        listing_id=uuid4(),
        stage=stage,
        agreed_price_kobo=4_800_000_000,
        created_at=datetime.now(UTC),
        property_title=title,
        sale_type="distress",
    )


class _StubRepo:
    def __init__(self, rows: list[DealRow]) -> None:
        self._rows = rows
        self.called_with: UUID | None = None

    async def list_for_buyer(self, buyer_id: UUID) -> list[DealRow]:
        self.called_with = buyer_id
        return self._rows


async def test_maps_rows_to_deal_items() -> None:
    repo = _StubRepo([_row("Duplex", "offer_accepted"), _row("Plot", "loan_applied")])
    buyer = uuid4()
    resp = await BuyerDealsService(transactions=repo).list_for_buyer(buyer)  # type: ignore[arg-type]

    assert repo.called_with == buyer
    assert [d.property_title for d in resp.data] == ["Duplex", "Plot"]
    assert resp.data[0].stage == "offer_accepted"
    assert resp.data[0].agreed_price_kobo == 4_800_000_000


async def test_empty() -> None:
    resp = await BuyerDealsService(transactions=_StubRepo([])).list_for_buyer(uuid4())  # type: ignore[arg-type]
    assert resp.data == []
