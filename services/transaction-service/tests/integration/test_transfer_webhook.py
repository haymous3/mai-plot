"""Integration tests for the payout (transfer) webhook (SCRUM-145) — real DB.

Seeds a payout payment_event left `processing` by a disbursement that placed an
async Paystack transfer (SCRUM-145 PR2), then POSTs a signed transfer.success /
transfer.failed to the real endpoint and asserts the payment_event is finalised
exactly once. The escrow debit is NOT reversed on failure — that's the
reconciliation sweep's job (backlog).
"""

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

pytestmark = pytest.mark.asyncio

_AMOUNT = 100_000_000  # ₦1M payout — under the ₦10M dual-approval threshold
# Matches the config default paystack_webhook_secret (env unset in tests).
_WEBHOOK_SECRET = "change-me-paystack-webhook-secret"


def _signed(body: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    sig = hmac.new(_WEBHOOK_SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return raw, {"x-paystack-signature": sig, "content-type": "application/json"}


def _transfer_body(event: str, pe_id: UUID) -> dict[str, object]:
    return {
        "event": event,
        "data": {
            "reference": str(pe_id),
            "transfer_code": "TRF_live_1",
            "status": event.split(".")[1],
        },
    }


def _seed_payout_event(
    db_engine: Engine,
    *,
    payer: UUID,
    payee: UUID,
    transaction_id: UUID,
    payment_type: str = "realtor_commission",
    status: str = "processing",
) -> UUID:
    """A payout event mid-flight: the disbursement placed an async transfer and
    left the event `processing` for this webhook to finalise."""
    pe_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, payee_id, "
                "transaction_id, amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :payee, :tid, :amt, :ptype, 'paystack', :status)"
            ),
            {
                "id": pe_id,
                "ik": uuid4(),
                "payer": payer,
                "payee": payee,
                "tid": transaction_id,
                "amt": _AMOUNT,
                "ptype": payment_type,
                "status": status,
            },
        )
    return pe_id


def _seed_transaction(db_engine: Engine, *, buyer: UUID, seller: UUID) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, 5000000000, 'completed')"
            ),
            {"id": tx_id, "lid": uuid4(), "bid": buyer, "sid": seller},
        )
    return tx_id


def _status(db_engine: Engine, pe_id: UUID) -> tuple[str, str | None]:
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, provider_reference FROM payment_events WHERE id = :id"),
            {"id": pe_id},
        ).one()
        return row.status, row.provider_reference


async def test_transfer_success_settles_payout(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller)
    pe_id = _seed_payout_event(db_engine, payer=seller, payee=realtor, transaction_id=tx_id)

    raw, headers = _signed(_transfer_body("transfer.success", pe_id))
    resp = await http_client.post("/webhooks/paystack", content=raw, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "settled"
    assert _status(db_engine, pe_id) == ("completed", "TRF_live_1")


async def test_transfer_failed_marks_payout_failed(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer, seller = seed_user(role="buyer"), seed_user(role="seller")
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller)
    pe_id = _seed_payout_event(
        db_engine,
        payer=buyer,
        payee=seller,
        transaction_id=tx_id,
        payment_type="seller_disbursement",
    )

    raw, headers = _signed(_transfer_body("transfer.failed", pe_id))
    resp = await http_client.post("/webhooks/paystack", content=raw, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "failed"
    assert _status(db_engine, pe_id) == ("failed", "TRF_live_1")


async def test_duplicate_transfer_success_is_noop(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller)
    pe_id = _seed_payout_event(db_engine, payer=seller, payee=realtor, transaction_id=tx_id)
    raw, headers = _signed(_transfer_body("transfer.success", pe_id))

    first = await http_client.post("/webhooks/paystack", content=raw, headers=headers)
    second = await http_client.post("/webhooks/paystack", content=raw, headers=headers)

    assert first.json()["status"] == "settled"
    assert second.json()["status"] == "duplicate"  # Paystack retried — no re-settle
    assert _status(db_engine, pe_id)[0] == "completed"


async def test_late_transfer_failed_cannot_unsettle_completed_payout(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer, seller, realtor = (
        seed_user(role="buyer"),
        seed_user(role="seller"),
        seed_user(role="realtor"),
    )
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seller)
    pe_id = _seed_payout_event(
        db_engine, payer=seller, payee=realtor, transaction_id=tx_id, status="completed"
    )

    raw, headers = _signed(_transfer_body("transfer.failed", pe_id))
    resp = await http_client.post("/webhooks/paystack", content=raw, headers=headers)

    assert resp.json()["status"] == "ignored"
    assert _status(db_engine, pe_id)[0] == "completed"  # still settled


async def test_transfer_webhook_bad_signature_is_401(
    clean_tables: None, http_client: AsyncClient
) -> None:
    body = json.dumps(_transfer_body("transfer.success", uuid4())).encode()
    resp = await http_client.post(
        "/webhooks/paystack",
        content=body,
        headers={"x-paystack-signature": "wrong", "content-type": "application/json"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_SIGNATURE"
