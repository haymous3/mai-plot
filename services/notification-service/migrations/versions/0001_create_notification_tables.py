"""create notification tables: notifications

Revision ID: 0001_create_notification_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_notification_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # notifications — one row per delivery attempt across channels.
    # reference_type/reference_id is a soft polymorphic pointer (no FK
    # because the target table varies per type).
    op.execute(
        """
        CREATE TABLE notifications (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        UUID NOT NULL REFERENCES users(id),
            channel        VARCHAR(10) NOT NULL CHECK (channel IN ('push','sms','email','in_app')),
            type           VARCHAR(60) NOT NULL,
            title          VARCHAR(200),
            body           TEXT NOT NULL,
            reference_type VARCHAR(30),
            reference_id   UUID,
            is_read        BOOLEAN NOT NULL DEFAULT FALSE,
            sent_at        TIMESTAMPTZ,
            read_at        TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_notif_user ON notifications(user_id, is_read, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
