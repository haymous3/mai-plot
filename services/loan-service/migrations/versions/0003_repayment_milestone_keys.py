"""loan_repayment_milestones: upsert key for the repayment webhook (SCRUM-77)

Adds the unique key the repayment.milestone webhook upserts on — one milestone
per (loan_id, due_date). deleted_at already exists on this table (migration 0002),
so this only adds the index. Non-§11: not users/transactions/escrow.

Revision ID: 0003_repayment_milestone_keys
Revises: 0002_loan_idempotency
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_repayment_milestone_keys"
down_revision: str | None = "0002_loan_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One live milestone per (loan, due_date) — the upsert conflict target. Partial
    # so a future soft-delete + re-create of the same slot doesn't collide.
    op.execute(
        "CREATE UNIQUE INDEX uq_milestone_loan_due "
        "ON loan_repayment_milestones (loan_id, due_date) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_milestone_loan_due")
