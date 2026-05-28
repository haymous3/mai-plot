# mypy: disable-error-code="attr-defined,no-untyped-call,comparison-overlap"
"""Smoke test — proves db_session + UserFactory round-trip works end to
end. Inserts a row, asserts it's queryable inside the test transaction,
then the conftest rollback wipes it.

Module-level mypy ignore matches tests/factories.py — factory-boy lacks
the type stubs mypy --strict needs to track instance/class attribute
shapes across the factory machinery.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tests.factories import UserFactory, bind_factories


def test_user_factory_creates_row(db_session: Session) -> None:
    bind_factories(db_session)
    user = UserFactory(role="seller")
    db_session.flush()

    fetched = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert fetched.role == "seller"
    assert fetched.email == user.email
