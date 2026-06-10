"""AuditLog — append-only system audit trail (data-model.md §19).

Rows are INSERT-only: the repository never updates or deletes them. The
old_value/new_value JSON columns capture state transitions (e.g. a PoA
document upload moving poa_verified_status not_applicable -> pending).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.user import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    actor_role: Mapped[str | None] = mapped_column(String(20), default=None)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    ip_address: Mapped[str | None] = mapped_column(INET, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
