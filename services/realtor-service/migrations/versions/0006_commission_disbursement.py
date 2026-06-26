"""link a disbursed commission to its payment_event (SCRUM-86 PR-B)

When a commission is disbursed (the real money movement happens in
transaction-service), realtor-service flips the commission 'available' ->
'withdrawn' and records which payment_event paid it + when. Non-§11 table
(commissions is realtor-service's, not users/transactions/escrow_ledger).

Revision ID: 0006_commission_disburse
Revises: 0005_inspection_declined
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_commission_disburse"
down_revision: str | None = "0005_inspection_declined"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE commissions ADD COLUMN payment_event_id UUID")
    op.execute("ALTER TABLE commissions ADD COLUMN disbursed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE commissions DROP COLUMN IF EXISTS disbursed_at")
    op.execute("ALTER TABLE commissions DROP COLUMN IF EXISTS payment_event_id")
