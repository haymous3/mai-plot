# mypy: disable-error-code="attr-defined,no-untyped-call"
"""Smoke test for PropertyListingFactory + db_session.

property_listings has a FK to users(id), so the test seeds a user row
first via raw SQL (auth-service owns User and we keep services ORM-
independent — no cross-service model imports).

Module-level mypy ignore matches tests/factories.py.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import PropertyListing
from tests.factories import PropertyListingFactory, bind_factories


def _seed_user(session: Session, role: str = "seller") -> UUID:
    uid = uuid4()
    session.execute(
        text("INSERT INTO users (id, role) VALUES (:id, :role)"),
        {"id": uid, "role": role},
    )
    session.flush()
    return uid


def test_property_listing_factory_creates_row(db_session: Session) -> None:
    bind_factories(db_session)
    seller_id = _seed_user(db_session)
    listing = PropertyListingFactory(
        seller_id=seller_id, state="Lagos", asking_price_kobo=5_000_000_000
    )
    db_session.flush()

    fetched = db_session.execute(
        select(PropertyListing).where(PropertyListing.id == listing.id)
    ).scalar_one()
    assert fetched.state == "Lagos"
    assert fetched.asking_price_kobo == 5_000_000_000
    assert fetched.seller_id == seller_id
