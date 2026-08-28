"""SCRUM-192 — admin review of personal documents, and OCR escalations.

Two gaps closed here:

  * `user_documents` (My Documents, SCRUM-188) had no review path at all, so
    every upload was stuck on `pending` forever.
  * `under_review` — the status the OCR pipeline parks unreadable documents in
    *because they need a human* — was rejected by the review endpoint, so the
    escalation path ended nowhere.

The pre-existing listing-document behaviour is covered in
`test_document_review.py`; this file only exercises what SCRUM-192 added.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

# ==========================================================================
# Personal documents in the queue
# ==========================================================================


@pytest.mark.asyncio
async def test_personal_queue_lists_only_pending_personal_documents(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    seed_document(listing_id=listing_id, status="pending")
    buyer = seed_seller(phone="08011112222", role="buyer")
    seed_user_document(user_id=buyer, category="identity", file_name="nin-slip.pdf")
    seed_user_document(user_id=buyer, category="financial", status="verified")
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        "/admin/documents/queue?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # Exactly one pending personal document: the pending LISTING document must
    # not leak into this queue, nor the already-verified personal one.
    assert body["pagination"]["total"] == 1
    item = body["data"][0]
    assert item["source"] == "personal"
    assert item["file_name"] == "nin-slip.pdf"
    assert item["category"] == "identity"
    assert item["user_id"] == str(buyer)
    assert item["owner_name"] == "Seller"
    assert item["listing_id"] is None


@pytest.mark.asyncio
async def test_personal_queue_hides_soft_deleted_documents(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """A document its owner removed must not sit in a reviewer's queue."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    seed_user_document(user_id=buyer, deleted=True)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        "/admin/documents/queue?source=personal", headers=auth_header(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_queue_without_a_source_still_means_listing(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """Omitting source behaves exactly as the endpoint did before SCRUM-192."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    seed_document(listing_id=listing_id, status="pending")
    buyer = seed_seller(phone="08011112222", role="buyer")
    seed_user_document(user_id=buyer)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get("/admin/documents/queue", headers=auth_header(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["source"] == "listing"


# ==========================================================================
# Deciding a personal document
# ==========================================================================


@pytest.mark.asyncio
async def test_admin_verifies_personal_document(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """The gap SCRUM-188 left open: a My Documents upload can leave 'pending'."""
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify", "source": "personal"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "verified"
    assert response.json()["source"] == "personal"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT verification_status, verified_by_user_id FROM user_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.verification_status == "verified"
        assert str(row.verified_by_user_id) == str(admin)
        audit = conn.execute(
            text("SELECT action FROM audit_log WHERE entity_id = :id"),
            {"id": document_id},
        ).first()
        assert audit is not None
        assert audit.action == "document.verified"


@pytest.mark.asyncio
async def test_admin_rejects_personal_document_and_notes_are_required(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    bare = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "reject", "source": "personal"},
        headers=auth_header(token),
    )
    assert bare.status_code == 422
    assert_error_envelope(bare.json(), "NOTES_REQUIRED_FOR_REJECTION")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "reject", "source": "personal", "notes": "expired document"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    # "failed" is the stored value; the UI labels it "Rejected" (SCRUM-188).
    assert response.json()["verification_status"] == "failed"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT verification_status, verification_notes FROM user_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.verification_status == "failed"
        assert row.verification_notes == "expired document"


@pytest.mark.asyncio
async def test_personal_review_never_reaches_a_listing_document(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    """source=personal with a LISTING document id must 404 rather than fall
    through and quietly decide the listing document."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="pending")
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify", "source": "personal"},
        headers=auth_header(token),
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT verification_status FROM listing_documents WHERE id = :id"),
            {"id": document_id},
        ).first()
        assert row is not None
        assert row.verification_status == "pending"


@pytest.mark.asyncio
async def test_soft_deleted_personal_document_cannot_be_reviewed(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer, deleted=True)
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify", "source": "personal"},
        headers=auth_header(token),
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")


@pytest.mark.asyncio
async def test_owner_cannot_review_their_own_document(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_user_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    buyer = seed_seller(phone="08011112222", role="buyer")
    document_id = seed_user_document(user_id=buyer)
    token = mint_access_token(buyer, "buyer")

    response = await http_client.post(
        f"/admin/documents/{document_id}/review",
        json={"action": "verify", "source": "personal"},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "ADMIN_FORBIDDEN")


# ==========================================================================
# OCR escalations (under_review) are decidable
# ==========================================================================


@pytest.mark.asyncio
async def test_under_review_document_can_be_decided(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """OCR parks unreadable documents in under_review precisely because they
    need a human. Before SCRUM-192 the reviewer got 422 on exactly those."""
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="under_review")
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
        audit = conn.execute(
            text("SELECT old_value FROM audit_log WHERE entity_id = :id"),
            {"id": document_id},
        ).first()
        assert audit is not None
        # The audit log is append-only, so the prior status recorded here has
        # to be the real one rather than a hard-coded "pending".
        assert audit.old_value["verification_status"] == "under_review"


@pytest.mark.asyncio
async def test_under_review_documents_are_listable_as_a_queue(
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
    seed_document(listing_id=listing_id, status="under_review")
    admin = seed_seller(phone="08000000000", role="admin")
    token = mint_access_token(admin, "admin")

    response = await http_client.get(
        "/admin/documents/queue?status=under_review", headers=auth_header(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total"] == 1
