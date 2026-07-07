"""GET /listings/{id}/documents integration tests (SCRUM-95).

The buyer detail page's trust panel reads document verification metadata — type
+ status only, never an s3_key or URL.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_lists_document_verification_metadata(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    seed_document: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller)
    seed_document(listing_id=listing, document_type="c_of_o", status="verified")
    seed_document(listing_id=listing, document_type="survey_plan", status="pending")

    buyer = seed_seller(phone="08099999999", role="buyer")
    resp = await http_client.get(
        f"/listings/{listing}/documents", headers=auth_header(mint_access_token(buyer, "buyer"))
    )
    assert resp.status_code == 200, resp.text
    docs = resp.json()["documents"]
    assert {(d["document_type"], d["verification_status"]) for d in docs} == {
        ("c_of_o", "verified"),
        ("survey_plan", "pending"),
    }
    # Trust metadata only — the file location is never exposed here.
    for d in docs:
        assert "s3_key" not in d and "url" not in d


@pytest.mark.asyncio
async def test_empty_for_listing_without_documents(
    clean_tables: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller)
    buyer = seed_seller(phone="08099999999", role="buyer")
    resp = await http_client.get(
        f"/listings/{listing}/documents", headers=auth_header(mint_access_token(buyer, "buyer"))
    )
    assert resp.status_code == 200
    assert resp.json()["documents"] == []


@pytest.mark.asyncio
async def test_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get(f"/listings/{uuid4()}/documents")
    assert resp.status_code == 401
