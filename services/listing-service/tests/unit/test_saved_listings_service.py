"""Unit tests for SavedListingService (SCRUM-95)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import FeedRow
from app.services.saved_listings import SavedListingService

pytestmark = pytest.mark.asyncio


def _row(title: str) -> FeedRow:
    return FeedRow(
        id=uuid4(),
        title=title,
        property_type="land",
        state="Lagos",
        lga="Ikeja",
        size_sqm=Decimal("500"),
        asking_price_kobo=5_000_000_000,
        sale_type="normal",
        urgency_tag=None,
        expires_at=None,
        status="active",
        doc_verification_status="verified",
        view_count=0,
        interest_count=0,
        created_at=datetime.now(UTC),
        seller_authority_type="owner",
    )


class _StubSaved:
    def __init__(self, rows: list[FeedRow] | None = None) -> None:
        self.saved: list[tuple[UUID, UUID]] = []
        self.unsaved: list[tuple[UUID, UUID]] = []
        self._rows = rows or []

    async def save(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        self.saved.append((buyer_id, listing_id))

    async def unsave(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        self.unsaved.append((buyer_id, listing_id))

    async def list_saved_feed(self, buyer_id: UUID) -> list[FeedRow]:
        return self._rows


def _service(stub: _StubSaved) -> SavedListingService:
    return SavedListingService(saved=stub)  # type: ignore[arg-type]


async def test_save_delegates_to_repo() -> None:
    stub = _StubSaved()
    buyer, listing = uuid4(), uuid4()
    await _service(stub).save(buyer_id=buyer, listing_id=listing)
    assert stub.saved == [(buyer, listing)]


async def test_unsave_delegates_to_repo() -> None:
    stub = _StubSaved()
    buyer, listing = uuid4(), uuid4()
    await _service(stub).unsave(buyer_id=buyer, listing_id=listing)
    assert stub.unsaved == [(buyer, listing)]


async def test_list_saved_maps_rows_to_feed_items() -> None:
    stub = _StubSaved([_row("A"), _row("B")])
    resp = await _service(stub).list_saved(uuid4())
    assert [i.title for i in resp.data] == ["A", "B"]
    assert resp.pagination.total == 2
    # FeedRow.expires_at maps to the FeedItem.urgency_expires_at field.
    assert resp.data[0].urgency_expires_at is None


async def test_list_saved_empty() -> None:
    resp = await _service(_StubSaved([])).list_saved(uuid4())
    assert resp.data == []
    assert resp.pagination.total == 0
    assert resp.pagination.total_pages == 0
