"""create notification_preferences table (SCRUM-122)

Per-user, per-channel opt-out (push/sms/email). In-app has no flag — it's the
user's notification-centre record and is always written. Owned by
notification-service; NOT a CLAUDE.md §11 table.

Revision ID: 0003_notification_preferences
Revises: 0002_create_push_subscriptions
Create Date: 2026-06-24

(Revision id kept <= 32 chars for the alembic_version column.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_notification_preferences"
down_revision: str | None = "0002_create_push_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One row per user (created lazily on first PATCH/unsubscribe). A missing row
    # means "all defaults" (everything enabled) — an opt-out model.
    op.execute(
        """
        CREATE TABLE notification_preferences (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID NOT NULL UNIQUE REFERENCES users(id),
            push_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
            sms_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
            email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at    TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_preferences CASCADE")
