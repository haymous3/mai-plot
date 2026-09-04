"""inspection report review workflow (SCRUM-205)

A submitted report had no reviewed state at all: a realtor submitted and it sat
there. Adds the review columns an admin decision writes, plus the revision
counter that lets a rejected report be resubmitted.

Non-§11 table (`inspections` is realtor-service's own, not users / transactions
/ escrow_ledger), so no stop-and-ask — but it is still a migration.

Backfill: every row that already has a `report_submitted_at` becomes 'pending'.
Those reports are real and genuinely unreviewed; leaving them 'not_submitted'
would hide them from the queue forever.

Index: the review queue reads by status across ALL realtors, and every existing
index on `inspections` leads with `realtor_id` — so without this the queue is a
seq scan + sort. Same trap SCRUM-192 hit on `user_documents`.

Revision ID: 0007_inspection_report_review
Revises: 0006_commission_disburse
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_inspection_report_review"
down_revision: str | None = "0006_commission_disburse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = "'not_submitted','pending','approved','rejected'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE inspections ADD COLUMN report_review_status VARCHAR(20) "
        "NOT NULL DEFAULT 'not_submitted'"
    )
    op.execute(
        "ALTER TABLE inspections ADD CONSTRAINT inspections_report_review_status_check "
        f"CHECK (report_review_status IN ({_STATUSES}))"
    )
    op.execute("ALTER TABLE inspections ADD COLUMN report_reviewed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE inspections ADD COLUMN report_reviewed_by UUID REFERENCES users(id)")
    op.execute("ALTER TABLE inspections ADD COLUMN report_review_note TEXT")
    op.execute("ALTER TABLE inspections ADD COLUMN report_revision SMALLINT NOT NULL DEFAULT 1")

    # Already-submitted reports are unreviewed, not un-submitted.
    op.execute(
        "UPDATE inspections SET report_review_status = 'pending' "
        "WHERE report_submitted_at IS NOT NULL"
    )

    # The queue: pending reports across every realtor, oldest first.
    op.execute(
        "CREATE INDEX idx_inspections_report_review "
        "ON inspections(report_review_status, report_submitted_at) "
        "WHERE report_submitted_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_inspections_report_review")
    op.execute(
        "ALTER TABLE inspections DROP CONSTRAINT IF EXISTS inspections_report_review_status_check"
    )
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS report_revision")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS report_review_note")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS report_reviewed_by")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS report_reviewed_at")
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS report_review_status")
