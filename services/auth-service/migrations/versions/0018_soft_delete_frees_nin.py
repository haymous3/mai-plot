"""soft-deleting a user releases their NIN and BVN

Revision ID: 0018_soft_delete_frees_nin
Revises: 0017_linked_identity

SCRUM-227 — reported from the funnel: delete an account, try to sign up again
with the same NIN, and registration answers "This NIN has already been
verified". The account holding it is dead, and it holds it forever.

`idx_user_pii_nin_lookup` (0004) and `idx_user_pii_bvn_lookup` (0003) are
partial on `<col> IS NOT NULL` only — neither predicate has any way to know the
owning account was soft-deleted.

This is the SAME bug migration 0009 fixed for phone and 0010 fixed for email.
Those two predate 0003/0004 in intent but postdate them in time, and the
identifier columns were never brought along.

⚠️ IT IS WORSE HERE THAN FOR PHONE OR EMAIL. A person can get a new phone
number or a new email address. Nobody gets a new NIN. As it stood, deleting an
account locked that human out of the platform permanently, and — since
SCRUM-225 — also meant a deleted account's NIN could never link a second one.

The groundwork is already in place: 0009 added `user_pii.deleted_at` and the
trigger that mirrors `users.deleted_at` onto it, precisely because a Postgres
partial index may only reference columns of its own table. So this migration
only has to widen two predicates.

What is deliberately NOT changed
--------------------------------
`nin_hash` / `nin_lookup` / `nin_encrypted` on the dead row are LEFT INTACT.
Only the RESERVATION is released. The audit history AMLON/KYC relies on lives
in the transaction and audit-log tables and is untouched, and the widened index
still guarantees at most one LIVE account per identifier — which is the
invariant that actually matters.

Releasing is unconditional: a NIN used in a completed deal is released like any
other. Blocking someone's return over a past transaction would punish the wrong
thing, and the deal's own record does not depend on this index (product owner
confirmed, 2026-09-11).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_soft_delete_frees_nin"
down_revision: str | None = "0017_linked_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widening a satisfied unique constraint cannot fail: every value distinct
    # over ALL rows is still distinct over the live subset. Same reasoning as
    # 0009 and 0010.
    op.execute("DROP INDEX IF EXISTS idx_user_pii_nin_lookup")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_nin_lookup ON user_pii(nin_lookup) "
        "WHERE nin_lookup IS NOT NULL AND deleted_at IS NULL"
    )

    # BVN gets the same treatment in the same migration, ON PURPOSE. It is
    # uncollected by any UI since SCRUM-189, so nobody would hit it today — and
    # that is exactly why leaving it wrong would mean rediscovering this bug
    # from first principles the day a bank partner asks for a BVN.
    op.execute("DROP INDEX IF EXISTS idx_user_pii_bvn_lookup")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_bvn_lookup ON user_pii(bvn_lookup) "
        "WHERE bvn_lookup IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # ⚠️ Narrowing back CAN fail, and legitimately: if two accounts have held
    # the same NIN since the upgrade — one deleted, one live — restoring the
    # old predicate finds a duplicate. That is the bug being reverted to, not a
    # fault in the downgrade.
    op.execute("DROP INDEX IF EXISTS idx_user_pii_nin_lookup")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_nin_lookup "
        "ON user_pii(nin_lookup) WHERE nin_lookup IS NOT NULL"
    )
    op.execute("DROP INDEX IF EXISTS idx_user_pii_bvn_lookup")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_bvn_lookup "
        "ON user_pii(bvn_lookup) WHERE bvn_lookup IS NOT NULL"
    )
