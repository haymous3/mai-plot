"""PATCH /listings/{id} integration tests.

Helpers arrive as fixtures (seed_seller, seed_listing, mint_access_token,
auth_header, assert_error_envelope) — see conftest.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.asyncio
async def test_owner_can_edit_listing(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, title="Old", asking_price_kobo=1_000_000_000)
    token = mint_access_token(seller, "seller")

    response = await http_client.patch(
        f"/listings/{listing_id}",
        json={"title": "New Title", "asking_price_kobo": 2_500_000_000},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT title, asking_price_kobo FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).first()
        assert row is not None
        assert row.title == "New Title"
        assert row.asking_price_kobo == 2_500_000_000


@pytest.mark.asyncio
async def test_non_owner_cannot_edit(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    owner = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=owner)
    stranger = seed_seller(phone="08087654321")
    token = mint_access_token(stranger, "seller")

    response = await http_client.patch(
        f"/listings/{listing_id}", json={"title": "Hijack"}, headers=auth_header(token)
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NOT_LISTING_OWNER")


@pytest.mark.asyncio
async def test_admin_can_edit_any_listing(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    owner = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=owner)
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    response = await http_client.patch(
        f"/listings/{listing_id}", json={"title": "Admin Edit"}, headers=auth_header(token)
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_sold_listing_cannot_be_edited(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="sold")
    token = mint_access_token(seller, "seller")

    response = await http_client.patch(
        f"/listings/{listing_id}", json={"title": "Nope"}, headers=auth_header(token)
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "CANNOT_EDIT_SOLD_LISTING")


@pytest.mark.asyncio
async def test_convert_normal_to_distress(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, sale_type="normal")
    token = mint_access_token(seller, "seller")

    response = await http_client.patch(
        f"/listings/{listing_id}",
        json={"sale_type": "distress", "urgency_tag": "7_days"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT sale_type, urgency_tag FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).first()
        assert row is not None
        assert row.sale_type == "distress"
        assert row.urgency_tag == "7_days"


@pytest.mark.asyncio
async def test_patch_unknown_id_is_404(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    response = await http_client.patch(
        f"/listings/{uuid4()}", json={"title": "x"}, headers=auth_header(token)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "LISTING_NOT_FOUND")


@pytest.mark.asyncio
async def test_patch_requires_authentication(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    response = await http_client.patch(f"/listings/{listing_id}", json={"title": "x"})
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
