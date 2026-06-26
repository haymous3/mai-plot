"""Integration tests for the bank decision webhook (SCRUM-76) — real DB + HMAC."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import get_settings

pytestmark = pytest.mark.asyncio


def _seed_loan(
    db_engine: Engine, *, buyer_id: UUID, tx_id: UUID, partner_id: UUID, reference: str
) -> UUID:
    loan_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO loans
                    (id, transaction_id, buyer_id, bank_partner_id,
                     requested_amount_kobo, tenure_months, status, bank_reference_id)
                VALUES (:id, :tx, :buyer, :partner, 250000000, 12, 'under_review', :ref)
                """
            ),
            {
                "id": loan_id,
                "tx": tx_id,
                "buyer": buyer_id,
                "partner": partner_id,
                "ref": reference,
            },
        )
    return loan_id


def _loan_status(db_engine: Engine, loan_id: UUID) -> tuple[str, int | None]:
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, approved_amount_kobo FROM loans WHERE id = :id"),
            {"id": loan_id},
        ).one()
    return row.status, row.approved_amount_kobo


def _sign(body: dict[str, object]) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    secret = get_settings().bank_webhook_secret
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, sig


async def test_approved_webhook_updates_loan(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    loan_id = _seed_loan(
        db_engine, buyer_id=buyer, tx_id=tx_id, partner_id=partner, reference="BANK-REF-INT"
    )

    raw, sig = _sign(
        {
            "event": "loan.decision_ready",
            "data": {
                "reference": "BANK-REF-INT",
                "decision": "approved",
                "approved_amount_kobo": 200_000_000,
                "interest_rate_bps": 2200,
                "tenure_months": 12,
                "monthly_instalment_kobo": 18_000_000,
            },
        }
    )
    resp = await http_client.post("/webhooks/bank", content=raw, headers={"x-bank-signature": sig})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "decided"
    assert _loan_status(db_engine, loan_id) == ("approved", 200_000_000)


async def test_duplicate_webhook_is_noop(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx_id = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    loan_id = _seed_loan(
        db_engine, buyer_id=buyer, tx_id=tx_id, partner_id=partner, reference="BANK-REF-DUP"
    )
    body: dict[str, object] = {
        "event": "loan.decision_ready",
        "data": {"reference": "BANK-REF-DUP", "decision": "rejected"},
    }
    raw, sig = _sign(body)
    headers = {"x-bank-signature": sig}

    first = await http_client.post("/webhooks/bank", content=raw, headers=headers)
    second = await http_client.post("/webhooks/bank", content=raw, headers=headers)
    assert first.json()["status"] == "decided"
    assert second.json()["status"] == "duplicate"  # idempotent — bank retried
    assert _loan_status(db_engine, loan_id) == ("rejected", None)


async def test_bad_signature_is_401(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    raw = json.dumps({"event": "loan.decision_ready", "data": {}}).encode()
    resp = await http_client.post(
        "/webhooks/bank", content=raw, headers={"x-bank-signature": "deadbeef"}
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_SIGNATURE"


async def test_unknown_reference_returns_200_unknown(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    raw, sig = _sign(
        {"event": "loan.decision_ready", "data": {"reference": "GHOST", "decision": "approved"}}
    )
    resp = await http_client.post("/webhooks/bank", content=raw, headers={"x-bank-signature": sig})
    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown_loan"
