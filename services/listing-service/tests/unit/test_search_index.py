"""InMemorySearchIndex — filtering, full-text, geo, scoring, pagination."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.adapters.search_index import InMemorySearchIndex, SearchDoc, SearchParams

_NOW = datetime.now(UTC)


def _expires_in(days: float) -> datetime:
    return _NOW + timedelta(days=days)


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
async def test_distress_is_boosted_above_normal_in_default_ranking() -> None:
    # A distress listing expiring soon outranks a NEWER normal listing.
    normal = _doc(title="Fresh Normal", sale_type="normal", created_at=_NOW)
    distress = _doc(
        title="Urgent Distress",
        sale_type="distress",
        expires_at=_expires_in(3),
        created_at=_NOW - timedelta(days=10),
    )
    idx = await _index(normal, distress)
    hits, _ = await idx.search(SearchParams())
    assert [h.doc.title for h in hits] == ["Urgent Distress", "Fresh Normal"]


@pytest.mark.asyncio
async def test_soonest_expiring_distress_ranks_first() -> None:
    soon = _doc(title="2 days", sale_type="distress", expires_at=_expires_in(2))
    later = _doc(title="20 days", sale_type="distress", expires_at=_expires_in(20))
    idx = await _index(later, soon)
    hits, _ = await idx.search(SearchParams())
    assert [h.doc.title for h in hits] == ["2 days", "20 days"]


@pytest.mark.asyncio
async def test_distress_without_expiry_gets_no_boost() -> None:
    # No expiry -> no urgency boost; falls back to recency vs a newer normal.
    distress = _doc(
        title="No Expiry Distress",
        sale_type="distress",
        expires_at=None,
        created_at=_NOW - timedelta(days=5),
    )
    normal = _doc(title="Newer Normal", sale_type="normal", created_at=_NOW)
    idx = await _index(distress, normal)
    hits, _ = await idx.search(SearchParams())
    assert [h.doc.title for h in hits] == ["Newer Normal", "No Expiry Distress"]


@pytest.mark.asyncio
async def test_price_sort_ignores_urgency_boost() -> None:
    cheap_normal = _doc(title="Cheap", sale_type="normal", asking_price_kobo=1_000_000_000)
    pricey_distress = _doc(
        title="Pricey",
        sale_type="distress",
        expires_at=_expires_in(1),
        asking_price_kobo=9_000_000_000,
    )
    idx = await _index(pricey_distress, cheap_normal)
    hits, _ = await idx.search(SearchParams(sort="price_asc"))
    assert [h.doc.title for h in hits] == ["Cheap", "Pricey"]


@pytest.mark.asyncio
async def test_urgency_boost_applies_within_text_search() -> None:
    # Both match the query; the soon-expiring distress one is lifted above.
    normal = _doc(title="Lekki Normal", sale_type="normal", created_at=_NOW)
    distress = _doc(title="Lekki Distress", sale_type="distress", expires_at=_expires_in(1))
    idx = await _index(normal, distress)
    hits, _ = await idx.search(SearchParams(q="lekki"))
    assert [h.doc.title for h in hits] == ["Lekki Distress", "Lekki Normal"]


@pytest.mark.asyncio
async def test_delete_removes_from_index() -> None:
    doc = _doc(title="Gone")
    idx = await _index(doc)
    await idx.delete(doc.id)
    _, total = await idx.search(SearchParams())
    assert total == 0
