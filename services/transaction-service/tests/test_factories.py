# mypy: disable-error-code="attr-defined,no-untyped-call"
"""Smoke test for TransactionFactory + db_session.

transactions has FKs to users(id) for buyer_id and seller_id, so the
test seeds two user rows first via raw SQL.

Module-level mypy ignore matches tests/factories.py.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Transaction
from tests.factories import TransactionFactory, bind_factories


def _seed_user(session: Session, role: str) -> UUID:
    uid = uuid4()
    session.execute(
        text("INSERT INTO users (id, role) VALUES (:id, :role)"),
        {"id": uid, "role": role},
    )
    session.flush()
    return uid


def test_transaction_factory_creates_row(db_session: Session) -> None:
    bind_factories(db_session)
    buyer_id = _seed_user(db_session, "buyer")
    seller_id = _seed_user(db_session, "seller")

    txn = TransactionFactory(
        buyer_id=buyer_id, seller_id=seller_id, agreed_price_kobo=7_500_000_000
    )
    db_session.flush()

    fetched = db_session.execute(select(Transaction).where(Transaction.id == txn.id)).scalar_one()
    assert fetched.stage == "offer_accepted"
    assert fetched.agreed_price_kobo == 7_500_000_000
    assert fetched.buyer_id == buyer_id
    assert fetched.seller_id == seller_id
