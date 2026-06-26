"""Integration tests for loan disbursement → escrow + decision advance (SCRUM-128).

The credit and stage-advance services have no HTTP route (loan-service enqueues
their Celery tasks by name), so these drive the tasks' async `_run` helpers
against the real DB. The loan-aware deposit IS exposed, so it goes through the
HTTP route with a seeded approved loan.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.loan_disbursement import CreditRequest
from app.tasks.loan_disbursement import _run as run_credit
from app.tasks.loan_stage import _run as run_advance

pytestmark = pytest.mark.asyncio

_PRICE = 5_000_000_000
_LOAN = 2_000_000_000


def _seed_buyer(db_engine: Engine, *, email: str | None = "buyer@maiplot.ng") -> UUID:
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


def _seed_transaction(db_engine: Engine, *, buyer: UUID, seller: UUID, stage: str) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, :stage)"
            ),
            {
                "id": tx_id,
                "lid": uuid4(),
                "bid": buyer,
                "sid": seller,
                "price": _PRICE,
                "stage": stage,
            },
        )
    return tx_id


def _seed_approved_loan(
    db_engine: Engine, *, buyer: UUID, transaction_id: UUID, approved_kobo: int
) -> UUID:
    """Seed a bank_partner + an approved loan for the transaction (cross-service
    tables; cleaned by the users-CASCADE truncation in clean_tables)."""
    loan_id, partner_id = uuid4(), uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bank_partners (id, name, short_code, loan_min_kobo, loan_max_kobo, "
                "interest_rate_bps, min_tenure_months, max_tenure_months) "
                "VALUES (:id, 'Test Bank', :code, 1, 100000000000, 2000, 6, 60)"
            ),
            {"id": partner_id, "code": str(partner_id)[:18]},
        )
        conn.execute(
            text(
                "INSERT INTO loans (id, transaction_id, buyer_id, bank_partner_id, "
                "requested_amount_kobo, approved_amount_kobo, status, bank_decision_at) "
                "VALUES (:id, :tid, :bid, :pid, :req, :appr, 'approved', NOW())"
            ),
            {
                "id": loan_id,
                "tid": transaction_id,
                "bid": buyer,
                "pid": partner_id,
                "req": approved_kobo,
                "appr": approved_kobo,
            },
        )
    return loan_id


def _escrow_credits(db_engine: Engine, tx_id: UUID) -> list[int]:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT amount_kobo FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type = 'credit'"
            ),
            {"tid": tx_id},
        ).all()
    return [r.amount_kobo for r in rows]


async def test_credit_funds_escrow(
    clean_tables: None, db_engine: Engine, seed_user: Callable[..., UUID]
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(
        db_engine, buyer=buyer, seller=seed_user(role="seller"), stage="loan_approved"
    )
    loan_id = uuid4()

    outcome = await run_credit(
        CreditRequest(loan_id=loan_id, transaction_id=tx_id, buyer_id=buyer, amount_kobo=_LOAN)
    )
    assert outcome == "credited"
    assert _escrow_credits(db_engine, tx_id) == [_LOAN]

    with db_engine.connect() as conn:
        pe = conn.execute(
            text(
                "SELECT status, payment_type FROM payment_events "
                "WHERE transaction_id = :tid AND payment_type = 'loan_disbursement'"
            ),
            {"tid": tx_id},
        ).one()
    assert pe.status == "completed"


async def test_credit_idempotent_no_double(
    clean_tables: None, db_engine: Engine, seed_user: Callable[..., UUID]
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(
        db_engine, buyer=buyer, seller=seed_user(role="seller"), stage="loan_approved"
    )
    req = CreditRequest(loan_id=uuid4(), transaction_id=tx_id, buyer_id=buyer, amount_kobo=_LOAN)

    first = await run_credit(req)
    second = await run_credit(req)
    assert first == "credited"
    assert second == "already_credited"
    assert _escrow_credits(db_engine, tx_id) == [_LOAN]  # exactly one credit


async def test_stage_advances_on_approved(
    clean_tables: None, db_engine: Engine, seed_user: Callable[..., UUID]
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(
        db_engine, buyer=buyer, seller=seed_user(role="seller"), stage="loan_applied"
    )

    outcome = await run_advance(tx_id, "approved")
    assert outcome == "advanced"

    with db_engine.connect() as conn:
        stage = conn.execute(
            text("SELECT stage FROM transactions WHERE id = :id"), {"id": tx_id}
        ).scalar_one()
        event = conn.execute(
            text(
                "SELECT from_stage, to_stage FROM transaction_events "
                "WHERE transaction_id = :id AND event_type = 'loan_decision'"
            ),
            {"id": tx_id},
        ).one()
    assert stage == "loan_approved"
    assert (event.from_stage, event.to_stage) == ("loan_applied", "loan_approved")


async def test_stage_advance_wrong_stage_is_no_op(
    clean_tables: None, db_engine: Engine, seed_user: Callable[..., UUID]
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(
        db_engine, buyer=buyer, seller=seed_user(role="seller"), stage="payment_held"
    )
    outcome = await run_advance(tx_id, "approved")
    assert outcome == "no_op"

    with db_engine.connect() as conn:
        stage = conn.execute(
            text("SELECT stage FROM transactions WHERE id = :id"), {"id": tx_id}
        ).scalar_one()
    assert stage == "payment_held"  # unchanged


async def test_loan_reduces_required_deposit(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = _seed_buyer(db_engine)
    tx_id = _seed_transaction(
        db_engine, buyer=buyer, seller=seed_user(role="seller"), stage="loan_approved"
    )
    _seed_approved_loan(db_engine, buyer=buyer, transaction_id=tx_id, approved_kobo=_LOAN)
    headers = auth_header(mint_token(buyer, "buyer"))

    # Buyer funds price − loan → accepted.
    ok = await http_client.post(
        f"/transactions/{tx_id}/deposit",
        json={"idempotency_key": str(uuid4()), "amount_kobo": _PRICE - _LOAN},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    # Paying the full price now over-funds escrow → mismatch.
    bad = await http_client.post(
        f"/transactions/{tx_id}/deposit",
        json={"idempotency_key": str(uuid4()), "amount_kobo": _PRICE},
        headers=headers,
    )
    assert bad.status_code == 422
    assert bad.json()["error_code"] == "AMOUNT_MISMATCH"
