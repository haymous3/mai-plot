"""GET /listings (feed) + GET /listings/{id} (detail) integration tests.

Helpers arrive as fixtures (seed_seller, seed_listing, seed_media,
mint_access_token, auth_header, assert_error_envelope) — see conftest. The
disable_cache fixture forces the Postgres path so assertions are deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_feed_returns_only_active_listings(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08012345678")
    seed_listing(seller_id=seller, title="Active A")
    seed_listing(seller_id=seller, title="Active B")
    seed_listing(seller_id=seller, title="Pending", status="pending_review")

    response = await http_client.get("/listings")
    assert response.status_code == 200, response.text
    body = response.json()
    titles = {item["title"] for item in body["data"]}
    assert titles == {"Active A", "Active B"}
    assert body["pagination"]["total"] == 2
    # Feed items carry the seller authority joined from users.
    assert body["data"][0]["seller_authority_type"] == "owner"


@pytest.mark.asyncio
async def test_feed_filters_by_state_and_sale_type(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08012345678")
    seed_listing(seller_id=seller, state="Lagos", sale_type="normal", title="Lagos Normal")
    seed_listing(
        seller_id=seller, state="Abuja", sale_type="distress", urgency_tag="7_days", title="Abuja D"
    )

    by_state = await http_client.get("/listings", params={"state": "Abuja"})
    assert {i["title"] for i in by_state.json()["data"]} == {"Abuja D"}

    by_type = await http_client.get("/listings", params={"sale_type": "distress"})
    assert {i["title"] for i in by_type.json()["data"]} == {"Abuja D"}


@pytest.mark.asyncio
async def test_feed_pagination(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08012345678")
    for i in range(3):
        seed_listing(seller_id=seller, title=f"Plot {i}")

    response = await http_client.get("/listings", params={"page": 1, "page_size": 2})
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["total_pages"] == 2


@pytest.mark.asyncio
async def test_detail_happy_path_with_media(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_media: Callable[..., None],
) -> None:
    seller = seed_seller(phone="08012345678", seller_authority_type="owner")
    listing_id = seed_listing(seller_id=seller, sale_type="distress", urgency_tag="14_days")
    seed_media(listing_id=listing_id)

    response = await http_client.get(f"/listings/{listing_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(listing_id)
    assert body["seller"]["id"] == str(seller)
    assert body["seller"]["authority_type"] == "owner"
    assert body["location"]["lat"] == pytest.approx(6.5)
    assert body["location"]["lng"] == pytest.approx(3.4)
    assert len(body["media"]) == 1
    assert body["media"][0]["type"] == "photo"
    # Anonymous viewer -> no loan eligibility indicator.
    assert body["loan_eligibility_kobo"] is None


@pytest.mark.asyncio
async def test_detail_buyer_sees_loan_eligibility(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, asking_price_kobo=8_000_000_000)
    buyer = seed_seller(phone="08087654321", role="buyer", seller_authority_type=None)
    token = mint_access_token(buyer, "buyer")

    response = await http_client.get(f"/listings/{listing_id}", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["loan_eligibility_kobo"] == 4_000_000_000  # 50%


@pytest.mark.asyncio
async def test_detail_unknown_id_is_404(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.get(f"/listings/{uuid4()}")
    assert response.status_code == 404
    assert_error_envelope(response.json(), "LISTING_NOT_FOUND")
