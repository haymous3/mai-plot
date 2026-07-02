"""Integration tests for buyer loan-document upload/list (SCRUM-131)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio

_PDF = b"%PDF-1.4 loan statement body"


def _seed_bank_partner(db_engine: Engine) -> UUID:
    pid = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bank_partners
                    (id, name, short_code, loan_min_kobo, loan_max_kobo,
                     interest_rate_bps, min_tenure_months, max_tenure_months, is_active)
                VALUES (:id, 'Test Bank', :code, 1000000, 500000000, 2200, 6, 36, TRUE)
                """
            ),
            {"id": pid, "code": f"BANK{uuid4().hex[:6].upper()}"},
        )
    return pid


def _seed_loan(db_engine: Engine, *, buyer_id: UUID, partner_id: UUID) -> UUID:
    loan_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO loans
                    (id, transaction_id, buyer_id, bank_partner_id, requested_amount_kobo)
                VALUES (:id, :tx, :buyer, :partner, 30000000)
                """
            ),
            {"id": loan_id, "tx": uuid4(), "buyer": buyer_id, "partner": partner_id},
        )
    return loan_id


async def _upload(
    http_client: AsyncClient, loan_id: UUID, token: str, *, data: bytes = _PDF
) -> Any:
    return await http_client.post(
        f"/loans/{loan_id}/documents",
        data={"document_type": "bank_statement"},
        files={"file": ("statement.pdf", data, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_buyer_uploads_then_lists(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
) -> None:
    buyer = seed_seller(phone="08012345678", role="buyer")
    partner = _seed_bank_partner(db_engine)
    loan = _seed_loan(db_engine, buyer_id=buyer, partner_id=partner)
    token = mint_access_token(buyer, "buyer")

    up = await _upload(http_client, loan, token)
    assert up.status_code == 201, up.text
    assert up.json()["verification_status"] == "pending"

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM loan_documents WHERE loan_id = :l"), {"l": loan}
        ).scalar_one()
    assert count == 1

    listed = await http_client.get(
        f"/loans/{loan}/documents", headers={"Authorization": f"Bearer {token}"}
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["document_type"] == "bank_statement"
    assert items[0]["url"]  # a pre-signed view URL


async def test_stranger_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
) -> None:
    buyer = seed_seller(phone="08012345678", role="buyer")
    stranger = seed_seller(phone="08087654321", role="buyer")
    partner = _seed_bank_partner(db_engine)
    loan = _seed_loan(db_engine, buyer_id=buyer, partner_id=partner)

    resp = await _upload(http_client, loan, mint_access_token(stranger, "buyer"))
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_LOAN_OWNER"


async def test_unknown_loan_404(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
) -> None:
    buyer = seed_seller(phone="08012345678", role="buyer")
    resp = await _upload(http_client, uuid4(), mint_access_token(buyer, "buyer"))
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "LOAN_NOT_FOUND"


async def test_bad_format_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    doc_storage_fake: Any,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
) -> None:
    buyer = seed_seller(phone="08012345678", role="buyer")
    partner = _seed_bank_partner(db_engine)
    loan = _seed_loan(db_engine, buyer_id=buyer, partner_id=partner)

    resp = await _upload(http_client, loan, mint_access_token(buyer, "buyer"), data=b"not-a-doc")
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "DOCUMENT_FORMAT_INVALID"
