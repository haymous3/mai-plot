"""Integration tests for account.opened + loan.disbursed webhooks (SCRUM-129).

The tx-task producer is the no-op default (tx_tasks_enabled=false in CI), so these
assert loan-service's own state changes; the enqueue itself is unit-tested.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import get_settings

pytestmark = pytest.mark.asyncio


def _sign(body: dict[str, object]) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    secret = get_settings().bank_webhook_secret
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


async def _post(client: AsyncClient, body: dict[str, object]) -> dict[str, object]:
    raw, sig = _sign(body)
    resp = await client.post("/webhooks/bank", content=raw, headers={"x-bank-signature": sig})
    assert resp.status_code == 200, resp.text
    data: dict[str, object] = resp.json()
    return data


def _loan_row(db_engine: Engine, reference: str) -> tuple[str, bool]:
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, bank_account_opened FROM loans WHERE bank_reference_id = :r"),
            {"r": reference},
        ).one()
    return row.status, row.bank_account_opened


async def test_account_opened_sets_flag_then_duplicate(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-ACCT", status="approved")
    body: dict[str, object] = {"event": "account.opened", "data": {"reference": "REF-ACCT"}}

    first = await _post(http_client, body)
    second = await _post(http_client, body)
    assert first["status"] == "account_opened"
    assert second["status"] == "duplicate"  # bank retried — no-op

    status_, opened = _loan_row(db_engine, "REF-ACCT")
    assert opened is True
    assert status_ == "approved"  # account opening doesn't change loan status


async def test_disbursed_sets_status_then_duplicate(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    seed_loan(
        buyer_id=buyer,
        tx_id=tx,
        partner_id=partner,
        reference="REF-DISB",
        status="approved",
        approved_amount_kobo=200_000_000,
    )
    body: dict[str, object] = {"event": "loan.disbursed", "data": {"reference": "REF-DISB"}}

    first = await _post(http_client, body)
    second = await _post(http_client, body)
    assert first["status"] == "disbursed"
    assert second["status"] == "duplicate"  # already disbursed

    status_, _ = _loan_row(db_engine, "REF-DISB")
    assert status_ == "disbursed"


async def test_disbursed_unknown_loan(clean_tables: None, http_client: AsyncClient) -> None:
    out = await _post(http_client, {"event": "loan.disbursed", "data": {"reference": "NOPE"}})
    assert out["status"] == "unknown_loan"
