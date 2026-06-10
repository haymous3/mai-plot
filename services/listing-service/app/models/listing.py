"""PropertyListing model — maps to public.property_listings.

The underlying table is partitioned by created_at with composite primary
key (id, created_at) — see services/listing-service/migrations/versions/
for the schema. The composite PK is reflected here so SQLAlchemy can
match rows correctly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    """Per-service declarative base."""


class PropertyListing(Base):
    __tablename__ = "property_listings"

    # Composite PK matches the partitioned table definition.
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )

    seller_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    property_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    address_text: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(Geography("POINT", srid=4326), nullable=False)
    lga: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    size_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    asking_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sale_type: Mapped[str] = mapped_column(String(20), nullable=False)
    urgency_tag: Mapped[str | None] = mapped_column(String(10), default=None)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
