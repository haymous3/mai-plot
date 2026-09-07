"""an inspection can exist before a realtor does: status 'unassigned'

Revision ID: 0008_unassigned_inspections
Revises: 0007_inspection_report_review
Create Date: 2026-09-06

SCRUM-208 — when nobody is in range, `POST /inspections` used to answer 503 and
the request was gone: the only trace was a `logger.warning`, and the 503's own
message ("An admin has been alerted") was not true. The buyer had asked for an
inspection and there was nothing left to act on.

An inspection now exists from the moment it is REQUESTED, with or without a
realtor. That turns a dropped request into a row an admin can place, and lets
the reassignment sweep pick it up when a realtor becomes eligible.

Three changes, each forced by "the realtor is not known yet"
------------------------------------------------------------
  * `realtor_id` NULLABLE — there is no realtor to name.
  * `status` gains `'unassigned'` — distinct from 'pending', which means "a
    named realtor has been offered this and has not yet accepted". Collapsing
    the two would make `/inspections/mine` and the acceptance window meaningless
    for half the rows in the status.
  * `assignment_expires_at` NULLABLE — the 2-hour ACCEPTANCE window belongs to
    an offer. An unassigned row has no offer outstanding, so a deadline on it
    would be a lie, and NOW() would make it instantly "lapsed" to the sweep.

Why not a separate `inspection_requests` table
----------------------------------------------
Because the request IS the inspection at an earlier stage. A second table would
duplicate the whole lifecycle, and placing a realtor would mean moving a row
between tables while `/inspections/by-transaction`, `/inspections/mine` and the
report endpoints each learned about both. Here, placement is an UPDATE that
fills `realtor_id` and opens the window.

What is safe because of the status split
----------------------------------------
Every existing query keys off status or realtor_id and therefore ignores the new
rows without being changed:
  * `_ACTIVE_STATUSES = ('pending','accepted','rescheduled')` — the
    one-live-inspection-per-transaction guard. ⚠️ 'unassigned' IS added to that
    tuple in code (a transaction with an outstanding request must not accumulate
    a second one), but the constant lives in the repository, not here.
  * `list_lapsed_pending` filters `status = 'pending'`, so an unassigned row is
    never treated as a lapsed offer.
  * `/inspections/mine` filters `realtor_id = :caller`, and NULL never equals a
    caller id.

Safety: two nullability relaxations and one CHECK widening on `inspections`. No
data is rewritten and no existing row changes meaning. Not a §11 table
(users / transactions / escrow_ledger).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_unassigned_inspections"
down_revision: str | None = "0007_inspection_report_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE inspections ALTER COLUMN realtor_id DROP NOT NULL")
    op.execute("ALTER TABLE inspections ALTER COLUMN assignment_expires_at DROP NOT NULL")

    # The CHECK is unnamed in 0001 (inline on the column), so Postgres generated
    # `inspections_status_check`. Dropped and recreated rather than edited —
    # there is no ALTER for a CHECK's expression.
    op.execute("ALTER TABLE inspections DROP CONSTRAINT inspections_status_check")
    op.execute(
        """
        ALTER TABLE inspections ADD CONSTRAINT inspections_status_check
            CHECK (status IN ('unassigned','pending','accepted','rescheduled','completed','no_show'))
        """
    )

    # Belt and braces: an assigned row must name a realtor, and only an
    # unassigned one may omit it. Without this, a bug that nulls realtor_id on a
    # live assignment would be silently accepted now that the column is nullable.
    op.execute(
        """
        ALTER TABLE inspections ADD CONSTRAINT inspections_realtor_required_unless_unassigned
            CHECK (realtor_id IS NOT NULL OR status = 'unassigned')
        """
    )

    # The admin queue reads "every unassigned request, oldest first". Every
    # existing index on this table leads with realtor_id or transaction_id, so
    # without this the queue is a seq scan + sort — the same shape SCRUM-192
    # found on the document queue.
    op.execute(
        """
        CREATE INDEX idx_inspections_unassigned ON inspections (created_at)
            WHERE status = 'unassigned'
        """
    )


def downgrade() -> None:
    # Assign or drop the unassigned rows first — they cannot satisfy NOT NULL.
    op.execute("DELETE FROM inspections WHERE status = 'unassigned'")
    op.execute("DROP INDEX IF EXISTS idx_inspections_unassigned")
    op.execute(
        "ALTER TABLE inspections DROP CONSTRAINT IF EXISTS "
        "inspections_realtor_required_unless_unassigned"
    )
    op.execute("ALTER TABLE inspections DROP CONSTRAINT inspections_status_check")
    op.execute(
        """
        ALTER TABLE inspections ADD CONSTRAINT inspections_status_check
            CHECK (status IN ('pending','accepted','rescheduled','completed','no_show'))
        """
    )
    op.execute("ALTER TABLE inspections ALTER COLUMN assignment_expires_at SET NOT NULL")
    op.execute("ALTER TABLE inspections ALTER COLUMN realtor_id SET NOT NULL")
