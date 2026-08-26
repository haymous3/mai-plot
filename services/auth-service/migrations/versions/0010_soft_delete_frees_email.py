"""soft-deleting a user releases their email address

Revision ID: 0010_soft_delete_frees_email
Revises: 0009_soft_delete_frees_phone
Create Date: 2026-08-26

SCRUM-185 — the counterpart to 0009, which did this for the phone.

`users_email_key UNIQUE (email)` (migration 0001) ignores `deleted_at`, so a
soft-deleted account kept holding its address forever. Worse, it disagreed with
the application: `get_active_by_email` and `email_taken_by_other` BOTH filter
`deleted_at IS NULL`, so the service already believed a deleted user's address
was free. Registration therefore passed its own duplicate check and then hit
the constraint — surfacing as a 500 IntegrityError rather than a clean 400.

This narrows the constraint to a partial unique index over live rows only, so
the database and the service describe the same set.

Simpler than 0009: `email` and `deleted_at` are on the SAME table, so the index
predicate can reference `deleted_at` directly. No mirrored column, no trigger.
0009 needed both only because the phone lives on user_pii while deleted_at
lives on users, and a partial index cannot read across tables.

Safety
------
Narrowing a satisfied constraint cannot fail: every email is globally distinct
beforehand, so it is distinct within any subset.

Reusing a released address is safe against stale verification links. A token is
looked up by token_hash and carries user_id (email_verification_tokens), so it
resolves to the ORIGINAL account, never to whoever later takes the address. And
EmailVerificationService loads the account via get_active_by_id, which filters
deleted_at — so a deleted user's outstanding link is rejected as invalid rather
than verifying anything.

NULL emails are unaffected: Postgres permits duplicate NULLs in a unique index.

The downgrade can legitimately FAIL if an address was reused while this was
applied — two rows would then share it and the global constraint cannot be
rebuilt. Failing loudly is correct; the alternative is picking an account to
break on the operator's behalf.

§11 schema change on `users` — approved for this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_soft_delete_frees_email"
down_revision: str | None = "0009_soft_delete_frees_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The implicit constraint from `email VARCHAR(254) UNIQUE` in 0001;
    # Postgres names it <table>_<column>_key.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_email_key")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_email_live_unique ON users(email) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_email_live_unique")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)")
