"""/admin/listings queue + review integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.asyncio
async def test_admin_approve_activates_and_makes_searchable(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review", title="Pending Plot")
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    # Not searchable while pending.
    pre = await http_client.get("/listings/search", params={"q": "pending"})
    assert pre.json()["pagination"]["total"] == 0

    response = await http_client.post(
        f"/admin/listings/{listing_id}/review",
        json={"action": "approve"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).first()
        assert row is not None and row.status == "active"
        audit = conn.execute(
            text(
                "SELECT action, entity_type FROM audit_log "
                "WHERE entity_id = :id AND action = 'listing.active'"
            ),
            {"id": listing_id},
        ).first()
        assert audit is not None and audit.entity_type == "listing"

    # Re-indexed on approval -> now searchable.
    post = await http_client.get("/listings/search", params={"q": "pending"})
    assert post.json()["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_reject_requires_comment(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review")
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/listings/{listing_id}/review",
        json={"action": "reject"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "COMMENT_REQUIRED_FOR_REJECTION")


@pytest.mark.asyncio
async def test_reject_with_comment_sets_rejected(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review")
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/listings/{listing_id}/review",
        json={"action": "reject", "comment": "title docs unreadable"},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, rejection_reason FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).first()
        assert row is not None
        assert row.status == "rejected"
        assert row.rejection_reason == "title docs unreadable"


@pytest.mark.asyncio
async def test_non_admin_cannot_review(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="pending_review")
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/admin/listings/{listing_id}/review",
        json={"action": "approve"},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_review_non_pending_is_422(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/listings/{listing_id}/review",
        json={"action": "approve"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "LISTING_NOT_PENDING_REVIEW")


@pytest.mark.asyncio
async def test_queue_lists_pending_with_poa_first(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    owner = seed_seller(phone="08011111111", seller_authority_type="owner")
    poa = seed_seller(phone="08022222222", seller_authority_type="power_of_attorney")
    seed_listing(seller_id=owner, status="pending_review", title="Owner Pending")
    seed_listing(seller_id=poa, status="pending_review", title="PoA Pending")
    seed_listing(seller_id=owner, status="active", title="Already Active")
    admin = seed_seller(phone="08000000000", role="admin", seller_authority_type=None)
    token = mint_access_token(admin, "admin")

    response = await http_client.get("/admin/listings/queue", headers=auth_header(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    titles = [i["title"] for i in data]
    assert "Already Active" not in titles
    assert set(titles) == {"Owner Pending", "PoA Pending"}
    # PoA seller's listing is prioritised first.
    assert titles[0] == "PoA Pending"


@pytest.mark.asyncio
async def test_queue_requires_admin(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    response = await http_client.get("/admin/listings/queue", headers=auth_header(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_review_requires_auth(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.post(
        f"/admin/listings/{uuid4()}/review", json={"action": "approve"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
