# mypy: disable-error-code="attr-defined,no-untyped-call"
"""factory-boy factories for auth-service models.

Bound to the db_session fixture at use time via _bind_factory() so the
per-test transaction (with rollback) works. session_persistence="flush"
makes factory.create() round-trip to the DB to populate server-side
defaults without committing.

The module-level mypy ignore exists because factory-boy re-exports its
declarations (Sequence, LazyFunction, etc.) via star imports — mypy
--strict treats them as not explicitly exported and flags every use as
attr-defined, even though they work at runtime. Same applies to the
constructor calls (no-untyped-call) since factory-boy lacks type stubs.
"""

from __future__ import annotations

import factory
from sqlalchemy.orm import Session

from app.models import User


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"

    role = "buyer"
    email = factory.Sequence(lambda n: f"user{n}@maiplot.test")


def bind_factories(session: Session) -> None:
    """Wire every factory in this module to a session. Called by a per-test
    fixture so factories use the same transaction the test sees."""
    UserFactory._meta.sqlalchemy_session = session
