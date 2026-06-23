"""create push_subscriptions table (SCRUM-79)

Stores a user's Web Push subscriptions (one row per browser/device). Owned by
notification-service. Not a CLAUDE.md §11 table (users/transactions/escrow_ledger),
so no human sign-off required.

Revision ID: 0002_create_push_subscriptions
Revises: 0001_create_notification_tables
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_push_subscriptions"
down_revision: str | None = "0001_create_notification_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One row per (user, browser endpoint). endpoint is the push service URL the
    # browser hands us; p256dh + auth are the client's encryption keys from the
    # PushSubscription. A re-subscribe upserts on (user_id, endpoint) and revives
    # a soft-deleted row.
    op.execute(
        """
        CREATE TABLE push_subscriptions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id),
            endpoint    TEXT NOT NULL,
            p256dh      VARCHAR(255) NOT NULL,
            auth        VARCHAR(255) NOT NULL,
            user_agent  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ,
            UNIQUE (user_id, endpoint)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_push_sub_user ON push_subscriptions(user_id) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions CASCADE")
