"""Transaction model — maps to public.transactions.

Holds the current-state projection. transaction_events is the event-
sourced source of truth; this row's `stage` is whatever the latest
applied event sets it to.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    """Per-service declarative base."""


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    buyer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    seller_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    agreed_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="offer_accepted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
