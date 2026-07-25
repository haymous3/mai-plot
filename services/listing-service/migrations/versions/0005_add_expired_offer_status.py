"""add 'expired' to offers.status

Revision ID: 0005_add_expired_offer_status
Revises: 0004_add_paused_status
Create Date: 2026-07-25

An offer auto-expires 72h after it's made if the seller never responds (rule §4).
Until now expiry was enforced only lazily (transaction-service refused a stale
offer on read) and the status was never mutated. SCRUM-118 adds a proactive
Celery sweep that stamps status='expired', so this extends the offers status
CHECK to admit that value. The offers table is owned by listing-service.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_add_expired_offer_status"
down_revision: str | None = "0004_add_paused_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE offers DROP CONSTRAINT offers_status_check")
    op.execute(
        """
        ALTER TABLE offers ADD CONSTRAINT offers_status_check
        CHECK (status IN ('pending','accepted','rejected','countered','withdrawn','expired'))
        """
    )


def downgrade() -> None:
    # Fold any 'expired' rows back to 'rejected' before re-narrowing the CHECK.
    op.execute("UPDATE offers SET status = 'rejected' WHERE status = 'expired'")
    op.execute("ALTER TABLE offers DROP CONSTRAINT offers_status_check")
    op.execute(
        """
        ALTER TABLE offers ADD CONSTRAINT offers_status_check
        CHECK (status IN ('pending','accepted','rejected','countered','withdrawn'))
        """
    )
