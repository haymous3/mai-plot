"""Escrow admin endpoints integration tests (SCRUM-69) — real DB + JWT.

The payment flow (M3) creates payment_events and escrow entries; here we seed
them directly and exercise the read + dual-approval endpoints.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_THRESHOLD = 1_000_000_000  # ₦10M in kobo


def _seed_transaction(db_engine: Engine, *, buyer_id: UUID, seller_id: UUID) -> UUID:
    txn_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transactions
                    (id, listing_id, buyer_id, seller_id, agreed_price_kobo, stage)
                VALUES (:id, :lid, :bid, :sid, 5000000000, 'payment_held')
                """
            ),
            {"id": txn_id, "lid": uuid4(), "bid": buyer_id, "sid": seller_id},
        )
    return txn_id


def _seed_payment_event(
    db_engine: Engine, *, payer_id: UUID, transaction_id: UUID, amount_kobo: int
) -> UUID:
    pe_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO payment_events
                    (id, idempotency_key, payer_id, transaction_id, amount_kobo,
                     payment_type, provider)
                VALUES (:id, :ik, :payer, :tid, :amt, 'seller_disbursement', 'paystack')
                """
            ),
            {
                "id": pe_id,
                "ik": uuid4(),
                "payer": payer_id,
                "tid": transaction_id,
                "amt": amount_kobo,
            },
        )
    return pe_id


def _seed_entry(
    db_engine: Engine,
    *,
    transaction_id: UUID,
    payment_event_id: UUID,
    entry_type: str,
    amount_kobo: int,
    requires_dual: bool = False,
    approved_by_1: UUID | None = None,
    approved_by_2: UUID | None = None,
) -> UUID:
    eid = uuid4()
    approved_at = datetime.now(UTC) if approved_by_2 is not None else None
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO escrow_ledger
                    (id, transaction_id, entry_type, amount_kobo, description,
                     payment_event_id, requires_dual_approval, approved_by_1,
                     approved_by_2, approved_at)
                VALUES (:id, :tid, :et, :amt, 'seed', :peid, :dual, :by1, :by2, :appat)
                """
            ),
            {
                "id": eid,
                "tid": transaction_id,
                "et": entry_type,
                "amt": amount_kobo,
                "peid": payment_event_id,
                "dual": requires_dual,
                "by1": approved_by_1,
                "by2": approved_by_2,
                "appat": approved_at,
            },
        )
    return eid


@pytest.mark.asyncio
async def test_get_ledger_returns_balance_with_pending_debit(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin = seed_user(role="admin")
    txn = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)
    credit_pe = _seed_payment_event(
        db_engine, payer_id=buyer, transaction_id=txn, amount_kobo=5_000_000_000
    )
    debit_pe = _seed_payment_event(
        db_engine, payer_id=seller, transaction_id=txn, amount_kobo=2_000_000_000
    )
    _seed_entry(
        db_engine,
        transaction_id=txn,
        payment_event_id=credit_pe,
        entry_type="credit",
        amount_kobo=5_000_000_000,
    )
    _seed_entry(
        db_engine,
        transaction_id=txn,
        payment_event_id=debit_pe,
        entry_type="debit",
        amount_kobo=2_000_000_000,
        requires_dual=True,
        approved_by_1=admin,
    )

    response = await http_client.get(
        f"/admin/escrow/{txn}", headers=auth_header(mint_token(admin, "admin"))
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["balance_kobo"] == 5_000_000_000  # pending debit not deducted
    assert body["pending_kobo"] == 2_000_000_000
    assert len(body["entries"]) == 2


@pytest.mark.asyncio
async def test_second_approval_makes_debit_effective(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin_1 = seed_user(role="admin")
    admin_2 = seed_user(role="admin")
    txn = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)
    credit_pe = _seed_payment_event(
        db_engine, payer_id=buyer, transaction_id=txn, amount_kobo=5_000_000_000
    )
    debit_pe = _seed_payment_event(
        db_engine, payer_id=seller, transaction_id=txn, amount_kobo=2_000_000_000
    )
    _seed_entry(
        db_engine,
        transaction_id=txn,
        payment_event_id=credit_pe,
        entry_type="credit",
        amount_kobo=5_000_000_000,
    )
    entry = _seed_entry(
        db_engine,
        transaction_id=txn,
        payment_event_id=debit_pe,
        entry_type="debit",
        amount_kobo=2_000_000_000,
        requires_dual=True,
        approved_by_1=admin_1,
    )

    response = await http_client.post(
        f"/admin/escrow/{debit_pe}/approve", headers=auth_header(mint_token(admin_2, "admin"))
    )
    assert response.status_code == 200, response.text
    assert response.json()["approved_entry_ids"] == [str(entry)]

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT approved_by_2 FROM escrow_ledger WHERE id = :id"), {"id": entry}
        ).first()
        assert row is not None and str(row.approved_by_2) == str(admin_2)

    # Balance now reflects the disbursement.
    bal = await http_client.get(
        f"/admin/escrow/{txn}", headers=auth_header(mint_token(admin_2, "admin"))
    )
    assert bal.json()["balance_kobo"] == 3_000_000_000
    assert bal.json()["pending_kobo"] == 0


@pytest.mark.asyncio
async def test_same_admin_cannot_give_second_approval(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    admin_1 = seed_user(role="admin")
    txn = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)
    debit_pe = _seed_payment_event(
        db_engine, payer_id=seller, transaction_id=txn, amount_kobo=2_000_000_000
    )
    _seed_entry(
        db_engine,
        transaction_id=txn,
        payment_event_id=debit_pe,
        entry_type="debit",
        amount_kobo=2_000_000_000,
        requires_dual=True,
        approved_by_1=admin_1,
    )

    response = await http_client.post(
        f"/admin/escrow/{debit_pe}/approve", headers=auth_header(mint_token(admin_1, "admin"))
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "DUAL_APPROVAL_SAME_ADMIN"


@pytest.mark.asyncio
async def test_approve_with_nothing_pending_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    admin = seed_user(role="admin")
    response = await http_client.post(
        f"/admin/escrow/{uuid4()}/approve", headers=auth_header(mint_token(admin, "admin"))
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "NO_PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_non_admin_is_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    txn = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)
    response = await http_client.get(
        f"/admin/escrow/{txn}", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_FORBIDDEN"


@pytest.mark.asyncio
async def test_escrow_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
) -> None:
    response = await http_client.get(f"/admin/escrow/{uuid4()}")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"
