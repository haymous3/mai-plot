"""Integration tests for loan application (SCRUM-75) — real DB + JWT + fake bank."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio


def _loan_count(db_engine: Engine, buyer_id: UUID) -> int:
    with db_engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(*) FROM loans WHERE buyer_id = :b"), {"b": buyer_id}
            ).scalar_one()
        )


async def test_apply_submits_to_bank(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()

    resp = await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 300_000_000,
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
        },
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "under_review"
    assert body["bank_reference_id"].startswith("FAKE-BANK-")
    assert _loan_count(db_engine, buyer) == 1


async def test_apply_persists_applicant_fields(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    headers = auth_header(mint_token(buyer, "buyer"))

    resp = await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 300_000_000,
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
            "employment_status": "self_employed",
            "monthly_income_kobo": 90_000_000,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    loan_id = resp.json()["loan_id"]

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT employment_status, monthly_income_kobo FROM loans WHERE id = :id"),
            {"id": loan_id},
        ).one()
    assert row.employment_status == "self_employed"
    assert row.monthly_income_kobo == 90_000_000

    # And they surface on the loan detail for the reviewing admin/buyer.
    detail = await http_client.get(f"/loans/{loan_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["employment_status"] == "self_employed"
    assert body["monthly_income_kobo"] == 90_000_000


async def test_apply_invalid_employment_status_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    resp = await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 300_000_000,
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
            "employment_status": "astronaut",  # not in the allowed set
        },
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 422


async def test_apply_over_cap_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer, agreed_price_kobo=800_000_000)  # cap ₦4M
    partner = seed_bank_partner()

    resp = await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 450_000_000,  # > 50%
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
        },
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "LOAN_CAP_EXCEEDED"


async def test_apply_by_non_buyer_is_403(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    stranger = seed_user(role="buyer")

    resp = await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 100_000_000,
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
        },
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_TRANSACTION_BUYER"


async def test_apply_is_idempotent(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    headers = auth_header(mint_token(buyer, "buyer"))
    payload = {
        "transaction_id": str(tx_id),
        "bank_partner_id": str(partner),
        "requested_amount_kobo": 200_000_000,
        "tenure_months": 12,
        "idempotency_key": str(uuid4()),
    }

    first = await http_client.post("/loans/apply", json=payload, headers=headers)
    second = await http_client.post("/loans/apply", json=payload, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["loan_id"] == second.json()["loan_id"]
    assert _loan_count(db_engine, buyer) == 1  # one loan despite two POSTs


async def test_my_loans_lists_applications(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    headers = auth_header(mint_token(buyer, "buyer"))
    await http_client.post(
        "/loans/apply",
        json={
            "transaction_id": str(tx_id),
            "bank_partner_id": str(partner),
            "requested_amount_kobo": 100_000_000,
            "tenure_months": 12,
            "idempotency_key": str(uuid4()),
        },
        headers=headers,
    )

    resp = await http_client.get("/loans/me", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["transaction_id"] == str(tx_id)
