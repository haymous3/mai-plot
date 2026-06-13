"""POST /listings/{id}/documents integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_PDF = b"%PDF-1.4\nCertificate of Occupancy scan\n"


def _pdf(name: str = "cofo.pdf") -> dict[str, Any]:
    return {"file": (name, _PDF, "application/pdf")}


@pytest.mark.asyncio
async def test_owner_uploads_document(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files=_pdf(),
        data={"document_type": "c_of_o"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_status"] == "pending"
    document_id = body["document_id"]

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT listing_id, document_type, verification_status, s3_key "
                "FROM listing_documents WHERE id = :id"
            ),
            {"id": document_id},
        ).first()
        assert row is not None
        assert str(row.listing_id) == str(listing_id)
        assert row.document_type == "c_of_o"
        assert row.verification_status == "pending"
        assert row.s3_key.startswith(f"listings/{listing_id}/documents/")

    # Bytes landed in the (fake) private bucket.
    assert doc_storage_fake.data[row.s3_key] == _PDF


@pytest.mark.asyncio
async def test_non_owner_cannot_upload(
    clean_tables: None,
    doc_storage_fake: Any,
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

    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files=_pdf(),
        data={"document_type": "c_of_o"},
        headers=auth_header(token),
    )
    assert response.status_code == 403
    assert_error_envelope(response.json(), "NOT_LISTING_OWNER")


@pytest.mark.asyncio
async def test_bad_format_is_422(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")

    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files={"file": ("x.gif", b"GIF89a nope", "image/gif")},
        data={"document_type": "c_of_o"},
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "DOCUMENT_FORMAT_INVALID")


@pytest.mark.asyncio
async def test_unknown_listing_is_404(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    response = await http_client.post(
        f"/listings/{uuid4()}/documents",
        files=_pdf(),
        data={"document_type": "c_of_o"},
        headers=auth_header(token),
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), "LISTING_NOT_FOUND")


@pytest.mark.asyncio
async def test_invalid_document_type_is_422(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    token = mint_access_token(seller, "seller")
    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files=_pdf(),
        data={"document_type": "passport"},  # not an allowed type
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_upload_requires_auth(
    clean_tables: None,
    doc_storage_fake: Any,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller)
    response = await http_client.post(
        f"/listings/{listing_id}/documents",
        files=_pdf(),
        data={"document_type": "c_of_o"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")
