"""link a second account to the one that owns the NIN (SCRUM-225)

Revision ID: 0017_linked_identity
Revises: 0016_nin_encrypted

One person may hold more than one account — a seller who is also a realtor.
`idx_user_pii_nin_lookup` is UNIQUE, so the NIN can only ever live on ONE of
them. That index is the guard against one person quietly opening unlimited
accounts, and this migration deliberately does NOT touch it.

Instead the second account carries `linked_identity_user_id`, pointing at the
account that holds the verified NIN — the "root". Every sibling points at the
same root, never at each other, so:

  * "every account for this person" is one indexed query, and
  * a chain can never form, so resolving identity is a single hop, not a walk.

The root is enforced to be a root by a CHECK: a row that points at another row
cannot itself be pointed at... which SQL cannot express directly, so the
one-hop rule is enforced in the service layer (see AccountLinkService) and the
CHECK here only stops the degenerate self-reference.

ON DELETE RESTRICT matters less than it looks: account deletion in this system
is SOFT (users.deleted_at), so the FK never fires for the case we actually
care about. Blocking the soft delete of a root that still has children lives in
DeleteAccountService. The FK is here for hard deletes and for honesty about the
relationship.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017_linked_identity"
down_revision: str | None = "0016_nin_encrypted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable with no backfill: every existing account is its own root.
    op.execute("ALTER TABLE users ADD COLUMN linked_identity_user_id UUID")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_linked_identity "
        "FOREIGN KEY (linked_identity_user_id) REFERENCES users(id) ON DELETE RESTRICT"
    )
    # An account cannot be its own root — that would make the identity lookup
    # loop rather than terminate.
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_linked_identity_not_self "
        "CHECK (linked_identity_user_id IS NULL OR linked_identity_user_id <> id)"
    )
    # Partial: only linked rows are ever the subject of a sibling lookup, and
    # the overwhelming majority of rows are NULL.
    op.execute(
        "CREATE INDEX idx_users_linked_identity ON users(linked_identity_user_id) "
        "WHERE linked_identity_user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_linked_identity")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_linked_identity_not_self")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_linked_identity")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS linked_identity_user_id")
