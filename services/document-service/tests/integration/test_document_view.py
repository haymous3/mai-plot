"""GET /documents/{id}/view integration tests (incl. IDOR authorization)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_PDF = b"%PDF-1.4\nCertificate of Occupancy\n"


def _s3_key(db_engine: Engine, document_id: UUID) -> str:
    with db_engine.connect() as conn:
        key = conn.execute(
            text("SELECT s3_key FROM listing_documents WHERE id = :id"), {"id": document_id}
        ).scalar_one()
    return str(key)


@pytest.mark.asyncio
async def test_buyer_with_offer_views_watermarked_document(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    seed_offer: Callable[..., None],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="verified")
    doc_storage_fake.data[_s3_key(db_engine, document_id)] = _PDF

    buyer = seed_seller(phone="08087654321", role="buyer")
    seed_offer(listing_id=listing_id, buyer_id=buyer)  # the access relationship
    token = mint_access_token(buyer, "buyer")

    response = await http_client.get(f"/documents/{document_id}/view", headers=auth_header(token))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert b"WMARK[" in response.content
    assert b"%PDF-1.4" in response.content


@pytest.mark.asyncio
async def test_owner_can_view(
    clean_tables: None,
    doc_storage_fake: Any,
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
    document_id = seed_document(listing_id=listing_id, status="verified")
    doc_storage_fake.data[_s3_key(db_engine, document_id)] = _PDF
    token = mint_access_token(seller, "seller")

    response = await http_client.get(f"/documents/{document_id}/view", headers=auth_header(token))
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_unrelated_buyer_gets_404_not_the_document(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    # IDOR guard: a buyer with NO offer on the listing must not be able to
    # pull the document, and must not even learn it exists.
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    document_id = seed_document(listing_id=listing_id, status="verified")
    doc_storage_fake.data[_s3_key(db_engine, document_id)] = _PDF
    stranger = seed_seller(phone="08099999999", role="buyer")
    token = mint_access_token(stranger, "buyer")

    response = await http_client.get(f"/documents/{document_id}/view", headers=auth_header(token))
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")
    assert b"%PDF" not in response.content


@pytest.mark.asyncio
async def test_view_unverified_document_is_403(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
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
    doc_storage_fake.data[_s3_key(db_engine, document_id)] = _PDF
    token = mint_access_token(seller, "seller")  # owner, authorized

    response = await http_client.get(f"/documents/{document_id}/view", headers=auth_header(token))
    assert response.status_code == 403
    assert_error_envelope(response.json(), "DOCUMENT_NOT_VERIFIED")


@pytest.mark.asyncio
async def test_view_unknown_document_is_404(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    buyer = seed_seller(phone="08012345678", role="buyer")
    token = mint_access_token(buyer, "buyer")
    response = await http_client.get(f"/documents/{uuid4()}/view", headers=auth_header(token))
    assert response.status_code == 404
    assert_error_envelope(response.json(), "DOCUMENT_NOT_FOUND")


@pytest.mark.asyncio
async def test_view_requires_auth(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    response = await http_client.get(f"/documents/{uuid4()}/view")
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
