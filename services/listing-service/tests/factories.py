# mypy: disable-error-code="attr-defined,no-untyped-call"
"""factory-boy factories for listing-service models.

Module-level mypy ignore: factory-boy re-exports declarations via star
imports and lacks type stubs, so mypy --strict flags every Sequence /
LazyFunction use as attr-defined and every factory call as no-untyped-call.
"""

from __future__ import annotations

from uuid import uuid4

import factory
from sqlalchemy.orm import Session

from app.models import PropertyListing


class PropertyListingFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PropertyListing
        sqlalchemy_session_persistence = "flush"

    seller_id = factory.LazyFunction(uuid4)
    property_type = "land"
    title = factory.Sequence(lambda n: f"Test Plot #{n}")
    address_text = "1 Demo St, Lagos"
    # Lagos coordinates as a PostGIS POINT (WKT). GEOGRAPHY accepts WKT.
    location = "SRID=4326;POINT(3.4 6.5)"
    lga = "Eti-Osa"
    state = "Lagos"
    asking_price_kobo = 1_000_000_00  # ₦1,000,000 in kobo
    sale_type = "normal"


def bind_factories(session: Session) -> None:
    PropertyListingFactory._meta.sqlalchemy_session = session
