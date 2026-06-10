"""UserPii — sensitive fields kept out of the safely-cacheable users table.

Per data-model.md design principle #1, the join from users → user_pii is
the only place phone / full_name / BVN/NIN hashes live.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.user import Base


class UserPii(Base):
    __tablename__ = "user_pii"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    # full_name is NOT NULL in the DDL but the phone+OTP register flow does not
    # collect a name. Default to empty string; the profile-update flow (M1+)
    # will populate it. Avoids a schema migration on this PII table.
    full_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bvn_hash: Mapped[str | None] = mapped_column(String(128), default=None)
    # Deterministic HMAC-SHA256(bvn, pepper) for cross-account dedup; unique.
    # bvn_hash (bcrypt) verifies, bvn_lookup (HMAC) is the queryable key.
    bvn_lookup: Mapped[str | None] = mapped_column(String(64), default=None, unique=True)
    nin_hash: Mapped[str | None] = mapped_column(String(128), default=None)
    # Deterministic HMAC-SHA256(nin, pepper) for cross-account dedup; unique.
    nin_lookup: Mapped[str | None] = mapped_column(String(64), default=None, unique=True)
    # PoA document (SCRUM-48). Columns shipped in migration 0001; mapped here
    # when the upload handler first needs them. s3_key points at a PRIVATE
    # object served only via pre-signed URL — never a public URL.
    poa_document_s3_key: Mapped[str | None] = mapped_column(String(512), default=None)
    poa_document_owner_name: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
