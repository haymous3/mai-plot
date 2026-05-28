# mypy: disable-error-code="attr-defined,no-untyped-call"
"""factory-boy factories for transaction-service models.

Module-level mypy ignore: factory-boy lacks the type stubs mypy --strict
needs (Sequence/LazyFunction/etc. are star-imported).
"""

from __future__ import annotations

from uuid import uuid4

import factory
from sqlalchemy.orm import Session

from app.models import Transaction


class TransactionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Transaction
        sqlalchemy_session_persistence = "flush"

    listing_id = factory.LazyFunction(uuid4)
    buyer_id = factory.LazyFunction(uuid4)
    seller_id = factory.LazyFunction(uuid4)
    agreed_price_kobo = 5_000_000_00  # ₦5,000,000 in kobo
    stage = "offer_accepted"


def bind_factories(session: Session) -> None:
    TransactionFactory._meta.sqlalchemy_session = session
