"""GET /documents/mine seller-documents integration tests (SCRUM-98)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.asyncio
async def test_lists_only_my_documents(
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
    other = seed_seller(phone="08099999999")
    mine = seed_listing(seller_id=seller)
    theirs = seed_listing(seller_id=other)

    doc = seed_document(listing_id=mine, document_type="c_of_o", status="verified")
    seed_document(listing_id=mine, document_type="survey_plan", status="pending")
    seed_document(listing_id=theirs, document_type="c_of_o")
    # Admin feedback on the rejected doc.
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE listing_documents SET verification_notes = :n WHERE id = :id"),
            {"n": "Looks good.", "id": doc},
        )

    resp = await http_client.get(
        "/documents/mine", headers=auth_header(mint_access_token(seller, "seller"))
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    types = {d["document_type"] for d in data}
    assert types == {"c_of_o", "survey_plan"}
    cofo = next(d for d in data if d["document_type"] == "c_of_o")
    assert cofo["property_title"] == "Plot"
    assert cofo["verification_notes"] == "Looks good."


@pytest.mark.asyncio
async def test_documents_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/documents/mine")
    assert resp.status_code == 401
