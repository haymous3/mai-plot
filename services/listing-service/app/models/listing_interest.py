"""ListingInterest model — a buyer's "Express Interest" in a listing (SCRUM-95).

Lighter than an offer. One row per (buyer, listing); the listing's
interest_count is bumped only on the first interest. listing_id is not an FK —
property_listings is partitioned with a composite PK.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.listing import Base


class ListingInterest(Base):
    __tablename__ = "listing_interests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    buyer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
