"""InMemorySearchIndex — filtering, full-text, geo, scoring, pagination."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.adapters.search_index import InMemorySearchIndex, SearchDoc, SearchParams


def _doc(**overrides: object) -> SearchDoc:
    base: dict[str, object] = {
        "id": uuid4(),
        "title": "3-Bed Apartment Lekki",
        "description": "sea view duplex",
        "property_type": "residential",
        "state": "Lagos",
        "lga": "Eti-Osa",
        "address_text": "12 Admiralty Way",
        "lat": 6.4281,
        "lng": 3.4219,
        "size_sqm": Decimal("120.00"),
        "asking_price_kobo": 8_000_000_000,
        "sale_type": "normal",
        "urgency_tag": None,
        "expires_at": datetime(2026, 9, 1, tzinfo=UTC),
        "status": "active",
        "doc_verification_status": "verified",
        "seller_authority_type": "owner",
        "view_count": 0,
        "interest_count": 0,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return SearchDoc(**base)  # type: ignore[arg-type]


async def _index(*docs: SearchDoc) -> InMemorySearchIndex:
    idx = InMemorySearchIndex()
    for d in docs:
        await idx.upsert(d)
    return idx


@pytest.mark.asyncio
async def test_only_active_listings_are_returned() -> None:
    idx = await _index(_doc(title="Active"), _doc(title="Pending", status="pending_review"))
    hits, total = await idx.search(SearchParams())
    assert total == 1
    assert hits[0].doc.title == "Active"


@pytest.mark.asyncio
async def test_full_text_matches_title_and_drops_non_matches() -> None:
    idx = await _index(_doc(title="Lekki Duplex"), _doc(title="Ikeja Bungalow"))
    hits, total = await idx.search(SearchParams(q="lekki"))
    assert total == 1
    assert hits[0].doc.title == "Lekki Duplex"
    assert hits[0].score > 0


@pytest.mark.asyncio
async def test_title_match_outranks_body_match() -> None:
    in_title = _doc(title="Garden Estate", description="x")
    in_body = _doc(title="Plain House", description="near the garden park")
    idx = await _index(in_body, in_title)
    hits, _ = await idx.search(SearchParams(q="garden"))
    assert [h.doc.title for h in hits] == ["Garden Estate", "Plain House"]


@pytest.mark.asyncio
async def test_geo_radius_filters_by_distance() -> None:
    near = _doc(title="Near", lat=6.4281, lng=3.4219)  # Lekki
    far = _doc(title="Far", lat=9.0579, lng=7.4951)  # Abuja (~530km)
    idx = await _index(near, far)
    hits, total = await idx.search(SearchParams(lat=6.4281, lng=3.4219, radius_km=10))
    assert total == 1
    assert hits[0].doc.title == "Near"


@pytest.mark.asyncio
async def test_structured_filters() -> None:
    idx = await _index(
        _doc(title="A", state="Lagos", sale_type="distress", asking_price_kobo=5_000_000_000),
        _doc(title="B", state="Abuja", sale_type="normal", asking_price_kobo=9_000_000_000),
    )
    hits, total = await idx.search(SearchParams(state="Abuja"))
    assert total == 1 and hits[0].doc.title == "B"

    hits, total = await idx.search(SearchParams(sale_type="distress"))
    assert total == 1 and hits[0].doc.title == "A"

    hits, total = await idx.search(SearchParams(price_min=8_000_000_000))
    assert total == 1 and hits[0].doc.title == "B"


@pytest.mark.asyncio
async def test_pagination() -> None:
    idx = await _index(*[_doc(title=f"L{i}") for i in range(5)])
    hits, total = await idx.search(SearchParams(page=1, page_size=2))
    assert total == 5
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_delete_removes_from_index() -> None:
    doc = _doc(title="Gone")
    idx = await _index(doc)
    await idx.delete(doc.id)
    _, total = await idx.search(SearchParams())
    assert total == 0
