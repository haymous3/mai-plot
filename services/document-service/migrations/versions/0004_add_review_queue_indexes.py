"""indexes for the admin review queue

Revision ID: 0004_review_queue_indexes
Revises: 0003_create_user_documents
Create Date: 2026-08-28

SCRUM-192 — the admin queue asks each document table one question:

    WHERE verification_status = :s [AND deleted_at IS NULL] ORDER BY created_at

Every existing index leads with the OWNER column (`idx_docs_listing` on
listing_id, `idx_user_docs_owner` on user_id), which answers "this listing's
documents" but does nothing for "every pending document". So both the COUNT and
the page were sequential scans plus a sort — fine on a demo database, and the
first thing to hurt once real uploads accumulate. The listing-document queue has
had this shape since SCRUM-23; it simply never had a UI to make it visible.

These indexes lead with `verification_status` and carry `created_at` so the
FIFO ordering is read straight from the index rather than sorted afterwards.

Safety
------
Index creation only — no data is read, written or moved, and no column or
constraint changes. Neither table is one of the §11 stop-and-ask tables
(users / transactions / escrow_ledger).

`CREATE INDEX` (not CONCURRENTLY) takes a write lock on the table for the
duration. That is the right trade here: both tables are small, and alembic runs
each migration inside a transaction, which CONCURRENTLY is not allowed to join.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_review_queue_indexes"
down_revision: str | None = "0003_create_user_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One statement per op.execute(): asyncpg runs these as prepared statements
    # and rejects multiple commands in one.
    #
    # Partial on deleted_at to match the query and stay small — user_documents
    # is soft-deleted, and a removed document never belongs in a queue.
    op.execute(
        "CREATE INDEX idx_user_docs_review_queue "
        "ON user_documents(verification_status, created_at) "
        "WHERE deleted_at IS NULL"
    )
    # listing_documents has no deleted_at, so no partial clause here.
    op.execute(
        "CREATE INDEX idx_listing_docs_review_queue "
        "ON listing_documents(verification_status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_listing_docs_review_queue")
    op.execute("DROP INDEX idx_user_docs_review_queue")
