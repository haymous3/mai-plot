"""GET /listings/search integration tests.

Search runs on the in-memory index fake (CI has no Elasticsearch). Tests seed
docs directly via the search_index_fake fixture, except the index-on-write
test which drives the real create endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.adapters.search_index import SearchDoc


def _doc(**overrides: object) -> SearchDoc:
    base: dict[str, object] = {
        "id": uuid4(),
        "title": "3-Bed Apartment Lekki",
        "description": "sea view",
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


@pytest.mark.asyncio
async def test_search_returns_active_matches_with_score(
    clean_listing_tables: None,
    search_index_fake: Any,
    http_client: AsyncClient,
) -> None:
    await search_index_fake.upsert(_doc(title="Lekki Duplex"))
    await search_index_fake.upsert(_doc(title="Ikeja Bungalow"))

    response = await http_client.get("/listings/search", params={"q": "lekki"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 1
    item = body["data"][0]
    assert item["title"] == "Lekki Duplex"
    assert item["search_score"] > 0


@pytest.mark.asyncio
async def test_default_search_boosts_soon_expiring_distress(
    clean_listing_tables: None,
    search_index_fake: Any,
    http_client: AsyncClient,
) -> None:
    from datetime import timedelta

    now = datetime.now(UTC)
    await search_index_fake.upsert(_doc(title="Fresh Normal", sale_type="normal", created_at=now))
    await search_index_fake.upsert(
        _doc(
            title="Urgent Distress",
            sale_type="distress",
            urgency_tag="7_days",
            expires_at=now + timedelta(days=2),
            created_at=now - timedelta(days=10),
        )
    )

    response = await http_client.get("/listings/search")
    assert response.status_code == 200, response.text
    titles = [item["title"] for item in response.json()["data"]]
    assert titles == ["Urgent Distress", "Fresh Normal"]


@pytest.mark.asyncio
async def test_search_geo_radius(
    clean_listing_tables: None,
    search_index_fake: Any,
    http_client: AsyncClient,
) -> None:
    await search_index_fake.upsert(_doc(title="Near", lat=6.4281, lng=3.4219))
    await search_index_fake.upsert(_doc(title="Far", lat=9.0579, lng=7.4951))

    response = await http_client.get(
        "/listings/search", params={"lat": 6.4281, "lng": 3.4219, "radius_km": 10}
    )
    assert response.status_code == 200
    titles = {i["title"] for i in response.json()["data"]}
    assert titles == {"Near"}


@pytest.mark.asyncio
async def test_search_excludes_pending(
    clean_listing_tables: None,
    search_index_fake: Any,
    http_client: AsyncClient,
) -> None:
    await search_index_fake.upsert(_doc(title="Live", status="active"))
    await search_index_fake.upsert(_doc(title="Draft", status="pending_review"))
    response = await http_client.get("/listings/search")
    assert {i["title"] for i in response.json()["data"]} == {"Live"}


@pytest.mark.asyncio
async def test_search_incomplete_geo_is_422(
    clean_listing_tables: None,
    search_index_fake: Any,
    http_client: AsyncClient,
) -> None:
    response = await http_client.get("/listings/search", params={"lat": 6.4})
    assert response.status_code == 422
    assert response.json()["error_code"] == "GEO_PARAMS_INCOMPLETE"


@pytest.mark.asyncio
async def test_creating_a_listing_indexes_it(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    # Drive the real create endpoint and prove index-on-write fired: the new
    # listing is pending_review, so it lands in the index but search (active
    # only) does not return it.
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    body = {
        "title": "Brand New Plot",
        "property_type": "land",
        "address_text": "1 Demo St",
        "location": {"lat": 6.5, "lng": 3.4},
        "lga": "Ikeja",
        "state": "Lagos",
        "asking_price_kobo": 5_000_000_000,
        "sale_type": "normal",
    }
    create = await http_client.post("/listings", json=body, headers=auth_header(token))
    assert create.status_code == 201, create.text
    listing_id = UUID(create.json()["listing_id"])

    # Index-on-write upserted the (pending) doc...
    assert listing_id in search_index_fake.docs
    assert search_index_fake.docs[listing_id].status == "pending_review"
    # ...but it is not yet searchable (search returns active only).
    search = await http_client.get("/listings/search", params={"q": "brand"})
    assert search.json()["pagination"]["total"] == 0
