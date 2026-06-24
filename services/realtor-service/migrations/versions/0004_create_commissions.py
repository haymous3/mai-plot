"""create commissions table (SCRUM-74)

Tracks the realtor commission accrued on a completed deal. This is
realtor-service's record of what each realtor is owed (BIGINT kobo); the actual
escrow_ledger movement + disbursement is deferred to M3 / SCRUM-86. NOT a §11
table (not users/transactions/escrow_ledger), and no money moves here.

Revision ID: 0004_create_commissions
Revises: 0003_realtor_base_location
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_create_commissions"
down_revision: str | None = "0003_realtor_base_location"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One commission per transaction (UNIQUE) so accrual is idempotent — the beat
    # can re-run safely. amount is BIGINT kobo (money non-negotiable). status:
    # pending -> available (after the 3-business-day hold) -> withdrawn (M3).
    op.execute(
        """
        CREATE TABLE commissions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            realtor_id      UUID NOT NULL REFERENCES users(id),
            transaction_id  UUID NOT NULL UNIQUE,
            inspection_id   UUID NOT NULL,
            amount_kobo     BIGINT NOT NULL CHECK (amount_kobo >= 0),
            rate_bps        INTEGER NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','available','withdrawn')),
            available_at    TIMESTAMPTZ NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_commissions_realtor ON commissions(realtor_id, status)")
    op.execute(
        "CREATE INDEX idx_commissions_pending_due ON commissions(available_at) "
        "WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS commissions CASCADE")
