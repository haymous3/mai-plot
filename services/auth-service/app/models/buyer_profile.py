"""BuyerProfile — optional "buying capacity" fields from buyer onboarding.

One row per buyer (SCRUM-132). Employment status, preferred location, and
budget are all optional (the onboarding screen has a "Skip for now"). budget is
stored as BIGINT kobo per the money rule. Kept out of `users` so the identity
row stays cache-safe and this can evolve without a users migration.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.user import Base


class BuyerProfile(Base):
    __tablename__ = "buyer_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    employment_status: Mapped[str | None] = mapped_column(String(30), default=None)
    preferred_location: Mapped[str | None] = mapped_column(String(120), default=None)
    budget_kobo: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
