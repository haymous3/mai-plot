"""Integration tests for buyer deposit checkout + webhook (SCRUM-83) — real DB."""

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

_PRICE = 5_000_000_000
# Matches the config default paystack_webhook_secret (env unset in tests).
_WEBHOOK_SECRET = "change-me-paystack-webhook-secret"


def _seed_buyer(db_engine: Engine, *, email: str | None = "buyer@maihomme.com") -> UUID:
    uid = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, role, email, verified_status, is_active) "
                "VALUES (:id, 'buyer', :email, 'id_verified', TRUE)"
            ),
            {"id": uid, "email": email},
        )
    return uid


def _seed_transaction(db_engine: Engine, *, buyer: UUID, seller: UUID) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES "
                "(:id, :lid, :bid, :sid, :price, 'inspection_completed')"
            ),
            {"id": tx_id, "lid": uuid4(), "bid": buyer, "sid": seller, "price": _PRICE},
        )
    return tx_id


def _seed_deposit_event(db_engine: Engine, *, buyer: UUID, transaction_id: UUID) -> UUID:
    pe_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, transaction_id, "
                "amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :tid, :amt, 'buyer_deposit', 'paystack', 'initiated')"
            ),
            {"id": pe_id, "ik": uuid4(), "payer": buyer, "tid": transaction_id, "amt": _PRICE},
        )
    return pe_id


def _signed(body: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    sig = hmac.new(_WEBHOOK_SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return raw, {"x-paystack-signature": sig, "content-type": "application/json"}


async def test_deposit_returns_checkout_url(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seed_user(role="seller"))

    resp = await http_client.post(
        f"/transactions/{tx_id}/deposit",
        json={"idempotency_key": str(uuid4()), "amount_kobo": _PRICE},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authorization_url"].startswith("https://checkout.paystack.test/pay/")
    assert body["authorization_url"].endswith(body["payment_event_id"])

    with db_engine.connect() as conn:
        pe = conn.execute(
            text("SELECT payment_type, status FROM payment_events WHERE id = :id"),
            {"id": body["payment_event_id"]},
        ).first()
        assert pe is not None
        assert pe.payment_type == "buyer_deposit"
        assert pe.status == "initiated"  # not credited until the webhook


async def test_deposit_non_buyer_is_403(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seed_user(role="seller"))
    stranger = seed_user(role="buyer")

    resp = await http_client.post(
        f"/transactions/{tx_id}/deposit",
        json={"idempotency_key": str(uuid4()), "amount_kobo": _PRICE},
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_TRANSACTION_BUYER"


async def test_deposit_amount_mismatch_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seed_user(role="seller"))

    resp = await http_client.post(
        f"/transactions/{tx_id}/deposit",
        json={"idempotency_key": str(uuid4()), "amount_kobo": _PRICE - 1},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "AMOUNT_MISMATCH"


async def test_webhook_charge_success_credits_escrow(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seed_user(role="seller"))
    pe_id = _seed_deposit_event(db_engine, buyer=buyer, transaction_id=tx_id)

    raw, headers = _signed(
        {"event": "charge.success", "data": {"reference": str(pe_id), "amount": _PRICE}}
    )
    resp = await http_client.post("/webhooks/paystack", content=raw, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "credited"

    with db_engine.connect() as conn:
        pe = conn.execute(
            text("SELECT status FROM payment_events WHERE id = :id"), {"id": pe_id}
        ).first()
        assert pe is not None and pe.status == "completed"
        credit = conn.execute(
            text(
                "SELECT amount_kobo FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type = 'credit'"
            ),
            {"tid": tx_id},
        ).first()
        assert credit is not None and credit.amount_kobo == _PRICE


async def test_webhook_bad_signature_is_401(clean_tables: None, http_client: AsyncClient) -> None:
    body = json.dumps({"event": "charge.success", "data": {}}).encode()
    resp = await http_client.post(
        "/webhooks/paystack",
        content=body,
        headers={"x-paystack-signature": "wrong", "content-type": "application/json"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "INVALID_SIGNATURE"


async def test_webhook_duplicate_does_not_double_credit(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(db_engine, buyer=buyer, seller=seed_user(role="seller"))
    pe_id = _seed_deposit_event(db_engine, buyer=buyer, transaction_id=tx_id)
    raw, headers = _signed(
        {"event": "charge.success", "data": {"reference": str(pe_id), "amount": _PRICE}}
    )

    first = await http_client.post("/webhooks/paystack", content=raw, headers=headers)
    second = await http_client.post("/webhooks/paystack", content=raw, headers=headers)
    assert first.json()["status"] == "credited"
    assert second.json()["status"] == "duplicate"

    with db_engine.connect() as conn:
        credits = conn.execute(
            text(
                "SELECT COUNT(*) FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type = 'credit'"
            ),
            {"tid": tx_id},
        ).scalar_one()
        assert credits == 1  # exactly one credit despite two webhooks
