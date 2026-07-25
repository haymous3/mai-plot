"""add notifications.archived_at + archive index

Revision ID: 0004_notification_archived_at
Revises: 0003_notification_preferences
Create Date: 2026-07-24

SCRUM-120 — a Celery beat archives notifications older than 90 days so the table
stays lean and the in-app centre never scans ancient rows. `archived_at` NULL =
live; a non-null stamp = archived (hidden from the centre, retained for audit).

A partial index on created_at WHERE archived_at IS NULL keeps the sweep's
"oldest un-archived first" scan cheap as the table grows.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_notification_archived_at"
down_revision: str | None = "0003_notification_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN archived_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX idx_notif_archive_sweep ON notifications(created_at) "
        "WHERE archived_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notif_archive_sweep")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS archived_at")
