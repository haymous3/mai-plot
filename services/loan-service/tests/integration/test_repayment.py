"""Integration tests for repayment tracking + title release (SCRUM-77)."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import date, timedelta
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


async def _post_webhook(client: AsyncClient, body: dict[str, object]) -> dict[str, object]:
    raw, sig = _sign(body)
    resp = await client.post("/webhooks/bank", content=raw, headers={"x-bank-signature": sig})
    assert resp.status_code == 200, resp.text
    data: dict[str, object] = resp.json()
    return data


def _milestone_row(db_engine: Engine, loan_id: UUID, due: date) -> tuple[str, int]:
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, amount_paid_kobo FROM loan_repayment_milestones "
                "WHERE loan_id = :l AND due_date = :d"
            ),
            {"l": loan_id, "d": due},
        ).one()
    return row.status, row.amount_paid_kobo


async def test_milestone_recorded_then_upserted(
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
    seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-MS")
    due = "2026-07-01"

    first = await _post_webhook(
        http_client,
        {
            "event": "repayment.milestone",
            "data": {
                "reference": "REF-MS",
                "due_date": due,
                "amount_due_kobo": 23_000_000,
                "amount_paid_kobo": 0,
                "status": "pending",
            },
        },
    )
    assert first["status"] == "recorded"

    # Same (loan, due_date) → upsert, not a duplicate row.
    second = await _post_webhook(
        http_client,
        {
            "event": "repayment.milestone",
            "data": {
                "reference": "REF-MS",
                "due_date": due,
                "amount_due_kobo": 23_000_000,
                "amount_paid_kobo": 23_000_000,
                "status": "paid",
            },
        },
    )
    assert second["status"] == "updated"
    status_, paid = _milestone_row(db_engine, _loan_id(db_engine, "REF-MS"), date(2026, 7, 1))
    assert status_ == "paid"
    assert paid == 23_000_000


def _loan_id(db_engine: Engine, reference: str) -> UUID:
    with db_engine.connect() as conn:
        loan_id: UUID = conn.execute(
            text("SELECT id FROM loans WHERE bank_reference_id = :r"), {"r": reference}
        ).scalar_one()
    return loan_id


async def test_fully_repaid_releases_title_then_duplicate(
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
    loan_id = seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-REPAID")
    body: dict[str, object] = {"event": "loan.fully_repaid", "data": {"reference": "REF-REPAID"}}

    first = await _post_webhook(http_client, body)
    second = await _post_webhook(http_client, body)
    assert first["status"] == "released"
    assert second["status"] == "duplicate"  # title already released — bank retried

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, title_released_at FROM loans WHERE id = :id"), {"id": loan_id}
        ).one()
    assert row.status == "fully_repaid"
    assert row.title_released_at is not None


async def test_buyer_sees_repayments_with_overdue_and_stranger_403(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    loan_id = seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-VIEW")

    past = (date.today() - timedelta(days=2)).isoformat()
    await _post_webhook(
        http_client,
        {
            "event": "repayment.milestone",
            "data": {
                "reference": "REF-VIEW",
                "due_date": past,
                "amount_due_kobo": 10_000_000,
                "amount_paid_kobo": 0,
                "status": "pending",  # past + pending → derived overdue
            },
        },
    )

    resp = await http_client.get(
        f"/loans/{loan_id}/repayments", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["progress"]["overdue_count"] == 1
    assert body["milestones"][0]["is_overdue"] is True

    stranger = seed_user(role="buyer")
    forbidden = await http_client.get(
        f"/loans/{loan_id}/repayments", headers=auth_header(mint_token(stranger, "buyer"))
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "NOT_LOAN_VIEWER"


async def test_admin_lists_active_loans_and_buyer_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    loan_id = seed_loan(
        buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-ADMIN", status="approved"
    )
    admin = seed_user(role="admin")

    ok = await http_client.get("/admin/loans", headers=auth_header(mint_token(admin, "admin")))
    assert ok.status_code == 200, ok.text
    ids = {item["loan_id"] for item in ok.json()["items"]}
    assert str(loan_id) in ids

    forbidden = await http_client.get(
        "/admin/loans", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert forbidden.status_code == 403
