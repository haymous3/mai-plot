"""Offer model — the pre-transaction negotiation (SCRUM-66).

A buyer's offer on a listing. Lives separately from `transactions` (which
begins at stage 'offer_accepted'): an offer moves through pending → countered →
accepted/rejected/expired, and ACCEPTING one creates a transactions row.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.transaction import Base


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    buyer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    seller_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    counter_amount_kobo: Mapped[int | None] = mapped_column(BigInteger, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    transaction_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
