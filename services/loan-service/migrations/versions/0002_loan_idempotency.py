"""loan idempotency key + soft-delete columns (SCRUM-75)

Adds the payment-idempotency anchor the loan application needs (CLAUDE.md §4:
UNIQUE(user_id, idempotency_key)) and the deleted_at soft-delete columns the loan
tables were missing vs §4. Non-§11 tables (loans/bank_partners/milestones are
loan-service's own, not users/transactions/escrow_ledger).

Revision ID: 0002_loan_idempotency
Revises: 0001_create_loan_tables
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_loan_idempotency"
down_revision: str | None = "0001_create_loan_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE loans ADD COLUMN idempotency_key UUID")
    # Partial unique index — one loan per (buyer, idempotency_key) when set.
    op.execute(
        "CREATE UNIQUE INDEX uq_loans_buyer_idem ON loans(buyer_id, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )
    op.execute("ALTER TABLE loans ADD COLUMN deleted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE bank_partners ADD COLUMN deleted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE loan_repayment_milestones ADD COLUMN deleted_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE loan_repayment_milestones DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE bank_partners DROP COLUMN IF EXISTS deleted_at")
    op.execute("DROP INDEX IF EXISTS uq_loans_buyer_idem")
    op.execute("ALTER TABLE loans DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE loans DROP COLUMN IF EXISTS idempotency_key")
