"""/admin/documents queue + review integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.asyncio
async def test_admin_verifies_document(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "verified"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT verification_status, verified_by_user_id "
                "FROM listing_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.verification_status == "verified"
        assert str(row.verified_by_user_id) == str(admin)
        audit = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE entity_id = :id AND action = 'document.verified'"
            ),
            {"id": document_id},
        ).first()
        assert audit is not None


@pytest.mark.asyncio
async def test_reject_requires_notes(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "reject"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "NOTES_REQUIRED_FOR_REJECTION")


@pytest.mark.asyncio
async def test_reject_marks_failed(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "reject", "notes": "wrong document"},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "failed"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT verification_status, verification_notes "
                "FROM listing_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.verification_status == "failed"
        assert row.verification_notes == "wrong document"


@pytest.mark.asyncio
async def test_non_admin_cannot_review(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id)
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify"},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_already_reviewed_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="verified")
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "DOCUMENT_NOT_PENDING")


@pytest.mark.asyncio
async def test_queue_lists_pending(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    seed_document(listing_id=listing_id, document_type="c_of_o", status="pending")
    seed_document(listing_id=listing_id, document_type="deed_of_assignment", status="pending")
    seed_document(listing_id=listing_id, document_type="receipt", status="verified")
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get("/admin/documents/queue", headers=auth_header(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 2
    types = {i["document_type"] for i in body["data"]}
    assert types == {"c_of_o", "deed_of_assignment"}


@pytest.mark.asyncio
async def test_review_requires_auth(
    clean_tables: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.post(
        f"/admin/documents/{uuid4()}/review", json={"action": "verify"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
