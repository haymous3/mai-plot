"""POST /listings integration tests.

Helpers (mint_access_token, seed_seller, auth_header, assert_error_envelope)
arrive as fixtures from conftest.py — NOT imported, to dodge the cross-service
`tests` package-name collision (every service has a tests.integration package).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_BODY: dict[str, Any] = {
    "title": "3-Bed Apartment Lekki Phase 1",
    "property_type": "residential",
    "description": "Spacious, sea view.",
    "address_text": "12 Admiralty Way, Lekki Phase 1, Lagos",
    "location": {"lat": 6.4281, "lng": 3.4219},
    "lga": "Eti-Osa",
    "state": "Lagos",
    "size_sqm": 120.5,
    "asking_price_kobo": 8_000_000_000,
    "sale_type": "normal",
}


@pytest.mark.asyncio
async def test_create_listing_happy_path(
    clean_listing_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller_id = seed_seller(phone="08012345678")
    token = mint_access_token(seller_id, "seller")

    response = await http_client.post("/listings", json=_BODY, headers=auth_header(token))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending_review"
    listing_id = body["listing_id"]

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT seller_id, status, sale_type, urgency_tag, expires_at, "
                "ST_AsText(location::geometry) AS loc FROM property_listings WHERE id = :id"
            ),
            {"id": listing_id},
        ).first()
        assert row is not None
        assert str(row.seller_id) == str(seller_id)
        assert row.status == "pending_review"
        assert row.sale_type == "normal"
        assert row.urgency_tag is None
        assert row.expires_at is not None
        assert row.loc == "POINT(3.4219 6.4281)"


@pytest.mark.asyncio
async def test_create_distress_listing_persists_urgency(
    clean_listing_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller_id = seed_seller(phone="08012345678")
    token = mint_access_token(seller_id, "seller")
    body = {**_BODY, "sale_type": "distress", "urgency_tag": "7_days"}

    response = await http_client.post("/listings", json=body, headers=auth_header(token))
    assert response.status_code == 201, response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT urgency_tag FROM property_listings WHERE id = :id"),
            {"id": response.json()["listing_id"]},
        ).first()
        assert row is not None and row.urgency_tag == "7_days"


@pytest.mark.asyncio
async def test_distress_without_urgency_is_422(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller_id = seed_seller(phone="08012345678")
    token = mint_access_token(seller_id, "seller")
    body = {**_BODY, "sale_type": "distress"}  # no urgency_tag

    response = await http_client.post("/listings", json=body, headers=auth_header(token))
    assert response.status_code == 422
    assert_error_envelope(response.json(), "URGENCY_TAG_REQUIRED_FOR_DISTRESS")


@pytest.mark.asyncio
async def test_buyer_cannot_create_listing(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    buyer_id = seed_seller(phone="08012345678", role="buyer", seller_authority_type=None)
    token = mint_access_token(buyer_id, "buyer")
    response = await http_client.post("/listings", json=_BODY, headers=auth_header(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "SELLER_ROLE_REQUIRED")


@pytest.mark.asyncio
async def test_unverified_seller_needs_identity(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller_id = seed_seller(
        phone="08012345678", verified_status="phone_verified", with_identity=False
    )
    token = mint_access_token(seller_id, "seller")
    response = await http_client.post("/listings", json=_BODY, headers=auth_header(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "BVN_REQUIRED")


@pytest.mark.asyncio
async def test_poa_seller_pending_cannot_publish(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller_id = seed_seller(
        phone="08012345678",
        seller_authority_type="power_of_attorney",
        poa_verified_status="pending",
    )
    token = mint_access_token(seller_id, "seller")
    response = await http_client.post("/listings", json=_BODY, headers=auth_header(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "POA_NOT_VERIFIED")


@pytest.mark.asyncio
async def test_poa_seller_verified_can_publish(
    clean_listing_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller_id = seed_seller(
        phone="08012345678",
        seller_authority_type="power_of_attorney",
        poa_verified_status="verified",
    )
    token = mint_access_token(seller_id, "seller")
    response = await http_client.post("/listings", json=_BODY, headers=auth_header(token))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_create_listing_requires_authentication(
    clean_listing_tables: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.post("/listings", json=_BODY)
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
