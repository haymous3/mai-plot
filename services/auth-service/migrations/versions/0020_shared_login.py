"""one sign-in for a person's buyer and seller accounts (SCRUM-236)

Revision ID: 0020_shared_login
Revises: 0019_first_last_name

A person who buys AND sells now has ONE email and ONE password. They land on
their buyer account and switch to the seller one (and back) from inside the
app. Each role is still its own `users` row — every other service keys its
data by user_id (listings by seller, offers by buyer, PoA state on the row), so
one row per role keeps all of that untouched. What changes is that the rows
share a login.

`shares_login_with_user_id` points a row at the account whose email + password
sign it in: the "login owner". Like SCRUM-225's `linked_identity_user_id` it is
ONE HOP — a sharer always points at an owner, never at another sharer — and the
service layer enforces that on write. The two columns are different things:
`linked_identity_user_id` says whose NIN this row inherits, this one says whose
credentials sign it in. A realtor who holds the NIN and has a separate seller
login is linked-identity but not shared-login, which is why this is a new
column rather than a reuse of 0017's.

The email index
---------------
`idx_users_email_live_unique` (0010) allowed one live row per address. A sharer
carries its owner's address — notification-service and every admin list read
`users.email` by id — so the index now covers LOGIN OWNERS only. It still
guarantees what it existed for: an email resolves to at most one account that
can be signed into. Sharers never answer an email lookup; the repository filters
them exactly as this predicate does.

The merge (product owner's decision, 2026-09-28)
-------------------------------------------------
Existing SCRUM-225 pairs — a buyer and a seller of the same person, each with
its own email and password — are folded onto one login here. For every live
sibling whose root is live, both being buyer/seller in different roles:

  * the sibling becomes a sharer of its ROOT (the account that holds the NIN
    and that confirmed the link from its own inbox), and
  * takes the root's email.

⚠️ So the sibling's own address and password STOP signing in. The person signs
in with the root's email and password and switches role inside the app. The
sibling's `auth_credentials` row is left in place (unreachable, since login only
ever resolves to an owner) rather than deleted, so nothing is destroyed that a
downgrade might want. The sibling's old email is overwritten and is NOT
recoverable from this migration.

Deliberately NOT merged: a pair whose root is a realtor (realtors are out of
scope for switching), and therefore two siblings that hang off a realtor root.
They keep separate logins exactly as before.

§11 schema change on `users` — approved for this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_shared_login"
down_revision: str | None = "0019_first_last_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN shares_login_with_user_id UUID")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_shares_login "
        "FOREIGN KEY (shares_login_with_user_id) REFERENCES users(id) ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_shares_login_not_self "
        "CHECK (shares_login_with_user_id IS NULL OR shares_login_with_user_id <> id)"
    )
    op.execute(
        "CREATE INDEX idx_users_shares_login ON users(shares_login_with_user_id) "
        "WHERE shares_login_with_user_id IS NOT NULL"
    )

    # Swap the email index BEFORE the merge: the merge writes an owner's address
    # onto a second live row, which the 0010 index would reject.
    op.execute("DROP INDEX IF EXISTS idx_users_email_live_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_email_login_unique ON users(email) "
        "WHERE deleted_at IS NULL AND shares_login_with_user_id IS NULL"
    )

    op.execute(
        "UPDATE users AS s "
        "SET shares_login_with_user_id = r.id, email = r.email, updated_at = now() "
        "FROM users AS r "
        "WHERE s.linked_identity_user_id = r.id "
        "AND s.deleted_at IS NULL AND r.deleted_at IS NULL "
        "AND s.role IN ('buyer', 'seller') AND r.role IN ('buyer', 'seller') "
        "AND s.role <> r.role"
    )


def downgrade() -> None:
    # A sharer has no address of its own to return to — the merge overwrote it
    # and a sharer created after the upgrade never had one. NULL is the only
    # value that satisfies the restored index; those rows can no longer be
    # signed into, which is the pre-0020 world's truth for them anyway.
    op.execute("UPDATE users SET email = NULL WHERE shares_login_with_user_id IS NOT NULL")
    op.execute("DROP INDEX IF EXISTS idx_users_email_login_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_email_live_unique ON users(email) WHERE deleted_at IS NULL"
    )
    op.execute("DROP INDEX IF EXISTS idx_users_shares_login")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_shares_login_not_self")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_shares_login")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS shares_login_with_user_id")
