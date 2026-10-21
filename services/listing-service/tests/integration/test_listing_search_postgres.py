"""GET /listings/search on the Postgres backend (SCRUM-251) — the default.

No search_index_fake here: every test seeds real property_listings rows and
queries the real generated search_vector column + PostGIS, which is what
production runs. test_listing_search.py keeps covering the same endpoint
through the in-memory fake.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.fixture
def seller(seed_seller: Callable[..., UUID]) -> UUID:
    return seed_seller(phone="08011112222")


@pytest.fixture
def set_columns(db_engine: Engine) -> Callable[..., None]:
    """seed_listing does not take every column; patch the rest directly."""

    def _set(listing_id: UUID, **cols: object) -> None:
        assignments = ", ".join(f"{name} = :{name}" for name in cols)
        with db_engine.begin() as conn:
            conn.execute(
                text(f"UPDATE property_listings SET {assignments} WHERE id = :id"),
                {**cols, "id": listing_id},
            )

    return _set


async def _titles(http_client: AsyncClient, **params: str | int | float) -> list[str]:
    response = await http_client.get("/listings/search", params=params)
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["data"]]


@pytest.mark.asyncio
async def test_text_query_matches_title_and_body_and_ranks_title_first(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
    set_columns: Callable[..., None],
) -> None:
    seed_listing(seller_id=seller, title="Lekki Duplex")
    body_hit = seed_listing(seller_id=seller, title="Four Bedroom House")
    set_columns(body_hit, description="Quiet street close to Lekki toll gate")
    seed_listing(seller_id=seller, title="Ikeja Bungalow")

    response = await http_client.get("/listings/search", params={"q": "lekki"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 2
    assert [i["title"] for i in body["data"]] == ["Lekki Duplex", "Four Bedroom House"]
    assert body["data"][0]["search_score"] > body["data"][1]["search_score"] > 0


@pytest.mark.asyncio
async def test_any_term_matches_and_stemming_applies(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
) -> None:
    # Multi-word queries OR their terms (ES multi_match default); "duplexes"
    # stems to "duplex".
    seed_listing(seller_id=seller, title="Lekki Duplex")
    seed_listing(seller_id=seller, title="Abuja Terrace")
    seed_listing(seller_id=seller, title="Ikeja Bungalow")

    assert set(await _titles(http_client, q="duplexes terrace")) == {
        "Lekki Duplex",
        "Abuja Terrace",
    }


@pytest.mark.asyncio
async def test_query_operators_are_not_interpreted(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
) -> None:
    # tsquery syntax in user input must neither error nor change the meaning.
    seed_listing(seller_id=seller, title="Lekki Duplex")
    assert await _titles(http_client, q="lekki & !duplex | (:*") == ["Lekki Duplex"]
    # Nothing searchable at all -> treated as no query, not a 500.
    assert await _titles(http_client, q="&&& !!") == ["Lekki Duplex"]


@pytest.mark.asyncio
async def test_only_active_live_rows_are_searchable(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
    set_columns: Callable[..., None],
) -> None:
    seed_listing(seller_id=seller, title="Live Plot")
    seed_listing(seller_id=seller, title="Pending Plot", status="pending_review")
    seed_listing(seller_id=seller, title="Paused Plot", status="paused")
    deleted = seed_listing(seller_id=seller, title="Deleted Plot")
    set_columns(deleted, deleted_at=datetime.now(UTC))

    assert await _titles(http_client, q="plot") == ["Live Plot"]


@pytest.mark.asyncio
async def test_status_change_is_reflected_without_any_sync(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
    set_columns: Callable[..., None],
) -> None:
    # The SCRUM-215 class: a paused listing stayed searchable because its ES
    # copy was never updated. With no copy, an UPDATE is the whole story.
    listing = seed_listing(seller_id=seller, title="Lekki Plot")
    assert await _titles(http_client, q="lekki") == ["Lekki Plot"]

    set_columns(listing, status="paused")
    assert await _titles(http_client, q="lekki") == []

    set_columns(listing, title="Banana Island Plot", status="active")
    assert await _titles(http_client, q="lekki") == []
    assert await _titles(http_client, q="banana") == ["Banana Island Plot"]


@pytest.mark.asyncio
async def test_filters(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
) -> None:
    seed_listing(seller_id=seller, title="Lagos Land", state="Lagos", property_type="land")
    seed_listing(
        seller_id=seller,
        title="Abuja House",
        state="FCT",
        lga="AMAC",
        property_type="residential",
        sale_type="distress",
        urgency_tag="7_days",
        asking_price_kobo=9_000_000_000,
        doc_verification_status="verified",
    )

    assert await _titles(http_client, state="FCT") == ["Abuja House"]
    assert await _titles(http_client, lga="Ikeja") == ["Lagos Land"]
    assert await _titles(http_client, sale_type="distress") == ["Abuja House"]
    assert await _titles(http_client, property_type="land") == ["Lagos Land"]
    assert await _titles(http_client, price_min=8_000_000_000) == ["Abuja House"]
    assert await _titles(http_client, price_max=8_000_000_000) == ["Lagos Land"]
    assert await _titles(http_client, doc_status="verified") == ["Abuja House"]


@pytest.mark.asyncio
async def test_geo_radius(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
) -> None:
    seed_listing(seller_id=seller, title="Near", lat=6.4281, lng=3.4219)
    seed_listing(seller_id=seller, title="Far", lat=9.0579, lng=7.4951)

    assert await _titles(http_client, lat=6.4281, lng=3.4219, radius_km=10) == ["Near"]


@pytest.mark.asyncio
async def test_default_ranking_boosts_soon_expiring_distress(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
    set_columns: Callable[..., None],
) -> None:
    now = datetime.now(UTC)
    fresh = seed_listing(seller_id=seller, title="Fresh Normal")
    set_columns(fresh, created_at=now)
    urgent = seed_listing(
        seller_id=seller, title="Urgent Distress", sale_type="distress", urgency_tag="7_days"
    )
    set_columns(urgent, expires_at=now + timedelta(days=2))

    assert await _titles(http_client) == ["Urgent Distress", "Fresh Normal"]


@pytest.mark.asyncio
async def test_price_sort_and_pagination(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    seed_listing: Callable[..., UUID],
) -> None:
    for title, price in (("Mid", 5_000_000_000), ("Low", 1_000_000_000), ("High", 9_000_000_000)):
        seed_listing(seller_id=seller, title=title, asking_price_kobo=price)

    assert await _titles(http_client, sort="price_asc") == ["Low", "Mid", "High"]
    assert await _titles(http_client, sort="price_desc") == ["High", "Mid", "Low"]

    response = await http_client.get(
        "/listings/search", params={"sort": "price_asc", "page": 2, "page_size": 2}
    )
    body = response.json()
    assert [i["title"] for i in body["data"]] == ["High"]
    assert body["pagination"] == {"page": 2, "page_size": 2, "total": 3, "total_pages": 2}


@pytest.mark.asyncio
async def test_new_listing_is_searchable_once_approved_with_no_index_step(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    set_columns: Callable[..., None],
) -> None:
    seller_id = seed_seller(phone="08012345678")
    token = mint_access_token(seller_id, "seller")
    create = await http_client.post(
        "/listings",
        json={
            "title": "Brand New Plot",
            "property_type": "land",
            "address_text": "1 Demo St",
            "location": {"lat": 6.5, "lng": 3.4},
            "lga": "Ikeja",
            "state": "Lagos",
            "asking_price_kobo": 5_000_000_000,
            "sale_type": "normal",
        },
        headers=auth_header(token),
    )
    assert create.status_code == 201, create.text
    listing_id = UUID(create.json()["listing_id"])

    # pending_review is not searchable...
    assert await _titles(http_client, q="brand") == []
    # ...and the moment the row is active, it is — nothing was dispatched.
    set_columns(listing_id, status="active")
    assert await _titles(http_client, q="brand") == ["Brand New Plot"]


@pytest.mark.asyncio
async def test_search_meets_the_latency_slo(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seller: UUID,
    db_engine: Engine,
) -> None:
    """CLAUDE.md §5: GET /listings/search p50 < 200ms, p99 < 500ms. Measured
    in-process over 1,000 listings with a text query, filters and a radius —
    the heaviest shape the endpoint accepts."""
    import time

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO property_listings
                    (seller_id, property_type, title, description, address_text, location,
                     lga, state, asking_price_kobo, sale_type, status)
                SELECT :sid, 'residential',
                       'Plot ' || g || CASE WHEN g % 7 = 0 THEN ' Lekki duplex' ELSE '' END,
                       'Listing number ' || g || ' with garden and parking',
                       g || ' Admiralty Way',
                       CAST(ST_SetSRID(ST_MakePoint(3.4 + g * 0.0001, 6.4), 4326) AS geography),
                       'Eti-Osa', 'Lagos', 1000000000 + g * 1000,
                       CASE WHEN g % 5 = 0 THEN 'distress' ELSE 'normal' END, 'active'
                FROM generate_series(1, 1000) AS g
                """
            ),
            {"sid": seller},
        )

    params: dict[str, str | float] = {
        "q": "lekki duplex",
        "state": "Lagos",
        "lat": 6.4,
        "lng": 3.45,
        "radius_km": 25,
    }
    await http_client.get("/listings/search", params=params)  # warm-up
    timings: list[float] = []
    for _ in range(50):
        started = time.perf_counter()
        response = await http_client.get("/listings/search", params=params)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    assert response.json()["pagination"]["total"] > 0

    timings.sort()
    p50, p99 = timings[len(timings) // 2], timings[int(len(timings) * 0.99) - 1]
    assert p50 < 0.200, f"p50 {p50 * 1000:.0f}ms"
    assert p99 < 0.500, f"p99 {p99 * 1000:.0f}ms"
