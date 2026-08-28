"""SCRUM-192 PR2 — GET /admin/documents/{id}/file.

The review queue was unusable end-to-end without this: `GET /documents/{id}/view`
serves only VERIFIED documents, to every caller including admins, so a reviewer
could list a pending document and never open it.
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
async def test_admin_opens_an_unverified_listing_document(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="pending")
    await doc_storage_fake.put(
        key=f"listings/{listing_id}/documents/{document_id}.pdf",
        data=b"%PDF-1.4 pending scan",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file", headers=auth_header(token)
    )

    assert response.status_code == 200, response.text
    assert response.content == b"%PDF-1.4 pending scan"
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline")


@pytest.mark.asyncio
async def test_the_buyer_route_still_refuses_the_same_unverified_document(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """The point of a separate route: /documents/{id}/view keeps its guard.

    An admin can reach the bytes through the review path and still cannot pull
    an unverified document through the path buyers and sellers use.
    """
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="pending")
    await doc_storage_fake.put(
        key=f"listings/{listing_id}/documents/{document_id}.pdf",
        data=b"%PDF-1.4 pending scan",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    review = await http_client.get(
        f"/admin/documents/{document_id}/file", headers=auth_header(token)
    )
    assert review.status_code == 200

    view = await http_client.get(f"/documents/{document_id}/view", headers=auth_header(token))
    assert view.status_code == 403
    assert_error_envelope(view.json(), "DOCUMENT_NOT_VERIFIED")


@pytest.mark.asyncio
async def test_admin_opens_a_personal_document(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer, file_name="nin-slip.pdf")
    await doc_storage_fake.put(
        key=f"users/{buyer}/documents/{document_id}.pdf",
        data=b"%PDF-1.4 nin slip",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )

    assert response.status_code == 200, response.text
    assert response.content == b"%PDF-1.4 nin slip"
    # The name the owner uploaded it under, not the uuid key.
    assert 'filename="nin-slip.pdf"' in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_every_access_is_audited(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Who opened whose identity document, and when — §9 (NDPR/AMLON)."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    await doc_storage_fake.put(
        key=f"users/{buyer}/documents/{document_id}.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 200

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT actor_id, action, entity_type, new_value FROM audit_log "
                "WHERE entity_id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.action == "document.viewed_for_review"
        assert str(row.actor_id) == str(admin)
        assert row.entity_type == "document"
        assert row.new_value == {"source": "personal"}


@pytest.mark.asyncio
async def test_non_admin_cannot_open_a_document_for_review(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """Not even the owner — this route deliberately ignores verification
    status, so it must stay admin-only."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    await doc_storage_fake.put(
        key=f"users/{buyer}/documents/{document_id}.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    token = mint_access_token(buyer, "buyer")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_requires_auth(
    clean_tables: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.get(f"/admin/documents/{uuid4()}/file")
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_soft_deleted_personal_document_is_not_served(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """The bytes survive deletion (AMLON retention, SCRUM-188) — but the
    document is gone as far as every API is concerned."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer, deleted=True)
    await doc_storage_fake.put(
        key=f"users/{buyer}/documents/{document_id}.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")


@pytest.mark.asyncio
async def test_missing_storage_object_is_404_and_not_audited(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """Row present, object absent. Nothing was read, so nothing is recorded as
    having been read."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) AS n FROM audit_log WHERE entity_id = :id"),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.n == 0


@pytest.mark.asyncio
async def test_personal_source_does_not_serve_a_listing_document(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="pending")
    await doc_storage_fake.put(
        key=f"listings/{listing_id}/documents/{document_id}.pdf",
        data=b"%PDF-1.4 seller paperwork",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")


@pytest.mark.asyncio
async def test_an_invalid_source_is_rejected(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{uuid4()}/file?source=everything", headers=auth_header(token)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_response_carries_nosniff(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """These bytes render inline on the admin's own origin, so the browser must
    not be free to sniff a different type out of them."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    await doc_storage_fake.put(
        key=f"users/{buyer}/documents/{document_id}.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        f"/admin/documents/{document_id}/file?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
