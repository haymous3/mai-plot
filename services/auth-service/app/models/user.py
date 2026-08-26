"""User model — maps to public.users from data-model.md / SCRUM-38.

Only the columns the factory + immediate handlers need; new columns get
added when a handler actually reads or writes them.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    """Per-service declarative base. Services are independent (CLAUDE.md §3)
    so each owns its own Base; no cross-service ORM coupling."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # NOT globally unique since SCRUM-185 (migration 0010): uniqueness is a
    # PARTIAL index over live rows only (WHERE deleted_at IS NULL), so a
    # soft-deleted account releases its address. `unique=True` here would
    # misdescribe the schema and emit the wrong DDL for a fresh create_all.
    email: Mapped[str | None] = mapped_column(String(254), default=None)
    verified_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unverified")
    seller_authority_type: Mapped[str | None] = mapped_column(String(30), default=None)
    poa_verified_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_applicable"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
