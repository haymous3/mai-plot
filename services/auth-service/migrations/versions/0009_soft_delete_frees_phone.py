"""soft-deleting a user releases their phone number

Revision ID: 0009_soft_delete_frees_phone
Revises: 0008_verification_channel
Create Date: 2026-08-26

SCRUM-184 — after 0008, a phone was reserved by the partial unique index
`WHERE verification_channel = 'phone'`, and that predicate had no way to know
the owning account had been soft-deleted. A deleted user therefore kept their
number reserved forever, and freeing it meant hand-editing
`verification_channel` on the dead row — which is what we were reduced to doing.

Two things were in the way:

  * the index cannot reference `users.deleted_at` — a Postgres partial index
    may only use columns of its own table, the same constraint that put
    `verification_channel` on user_pii in 0008; and
  * `user_pii` had no `deleted_at` of its own, despite CLAUDE.md §4 requiring
    one on every table.

So this adds `user_pii.deleted_at` and widens the predicate to
`WHERE verification_channel = 'phone' AND deleted_at IS NULL`.

Why a TRIGGER rather than doing it in the repository
----------------------------------------------------
Nothing in the application writes `users.deleted_at` today — there is no
soft-delete endpoint or repo method; every deletion so far has been manual SQL
against the database. An application-level "remember to update both tables"
rule cannot bind a human running psql, and forgetting fails SILENTLY: the
account disappears while its phone stays reserved, which is precisely the bug
being fixed.

The trigger makes the invariant hold for every writer — psql, a future admin
endpoint, a migration — rather than only for callers who remember. It fires
only when `deleted_at` actually changes, so ordinary updates are untouched.

Restoring a user (deleted_at back to NULL) re-reserves the phone. If someone
else claimed that number meanwhile, the trigger's UPDATE violates the unique
index and the whole transaction aborts. That is deliberate: failing loudly on
a genuine conflict beats silently leaving two live accounts on one number.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_soft_delete_frees_phone"
down_revision: str | None = "0008_verification_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_pii ADD COLUMN deleted_at TIMESTAMPTZ")

    # Backfill from the owning account so already-deleted users release their
    # numbers immediately, rather than only on some future delete.
    op.execute(
        """
        UPDATE user_pii p
        SET deleted_at = u.deleted_at
        FROM users u
        WHERE u.id = p.user_id AND u.deleted_at IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_user_pii_deleted_at() RETURNS trigger AS $$
        BEGIN
            UPDATE user_pii SET deleted_at = NEW.deleted_at WHERE user_id = NEW.id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    # `UPDATE OF deleted_at` narrows it to statements that touch the column;
    # the WHEN clause narrows further to those that actually change its value,
    # so a no-op rewrite does not churn user_pii.
    op.execute(
        """
        CREATE TRIGGER trg_users_deleted_at_sync
        AFTER UPDATE OF deleted_at ON users
        FOR EACH ROW
        WHEN (OLD.deleted_at IS DISTINCT FROM NEW.deleted_at)
        EXECUTE FUNCTION sync_user_pii_deleted_at()
        """
    )

    # Widen the predicate so a soft-deleted row stops reserving its phone.
    op.execute("DROP INDEX idx_user_pii_phone_channel_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_phone_channel_unique ON user_pii(phone) "
        "WHERE verification_channel = 'phone' AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # Narrowing back can legitimately FAIL: if two accounts now share a phone
    # because one was soft-deleted and the number re-claimed, the old index
    # cannot be rebuilt. Failing loudly is correct — the alternative is
    # choosing an account to break on the operator's behalf.
    op.execute("DROP INDEX IF EXISTS idx_user_pii_phone_channel_unique")
    op.execute("DROP TRIGGER IF EXISTS trg_users_deleted_at_sync ON users")
    op.execute("DROP FUNCTION IF EXISTS sync_user_pii_deleted_at()")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_phone_channel_unique ON user_pii(phone) "
        "WHERE verification_channel = 'phone'"
    )
    op.execute("ALTER TABLE user_pii DROP COLUMN deleted_at")
