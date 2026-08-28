"""allow the 'password_reset' token purpose, drop the unused 'reset' placeholder

Revision ID: 0012_password_reset_purpose
Revises: 0011_add_avatar_key
Create Date: 2026-08-28

SCRUM-191 — password reset reuses `email_verification_tokens` rather than
adding a table: it is already purpose-scoped, single-use (`used_at`), expiring,
and stores a SHA-256 digest of a 256-bit value. What it is NOT is open to a new
purpose — 0007 pinned the column with an inline CHECK, so an INSERT with a new
purpose fails with a check violation rather than being accepted.

Why not just use the existing 'reset' value
-------------------------------------------
0007 reserved 'reset' but nothing ever minted one, and the value is also a
member of the `EmailVerifyPurpose` Literal that POST /auth/verify/email accepts
from the client. That route mints a JWT pair on a valid token. Had reset tokens
been stored under 'reset', anyone holding a reset link could have POSTed it to
/auth/verify/email and been handed a live session — turning "reset my password"
into "log me in without one", and marking the address verified on the way.

So the reset purpose deliberately does NOT appear in that Literal, and the
reserved-but-unused value goes with it. Keeping a value in the CHECK that the
application refuses to accept only invites someone to wire it up later.

Safety
------
No rows can violate the new constraint: nothing has ever written 'reset' (0007
shipped it unused, and the only reference in the tree is a test that posts the
string to assert a purpose MISMATCH is rejected). The rewrite is a constraint
swap on a table outside the CLAUDE.md §11 set — `email_verification_tokens` is
not users / transactions / escrow_ledger — so no sign-off is required.

Postgres validates the new CHECK against existing rows, so an unexpected
'reset' row would fail the migration loudly rather than be silently orphaned.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_password_reset_purpose"
down_revision: str | None = "0011_add_avatar_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The inline CHECK from 0007 is auto-named <table>_<column>_check by
    # Postgres, same convention 0007 itself relied on for users.
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "DROP CONSTRAINT email_verification_tokens_purpose_check"
    )
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "ADD CONSTRAINT email_verification_tokens_purpose_check "
        "CHECK (purpose IN ('registration','login','password_reset'))"
    )


def downgrade() -> None:
    # Any reset token still on the table would violate the restored constraint,
    # so burn them first. They are short-lived (15 min) and single-use; losing
    # an unclicked link costs a user one more click on "Forgot password".
    op.execute("DELETE FROM email_verification_tokens WHERE purpose = 'password_reset'")
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "DROP CONSTRAINT email_verification_tokens_purpose_check"
    )
    op.execute(
        "ALTER TABLE email_verification_tokens "
        "ADD CONSTRAINT email_verification_tokens_purpose_check "
        "CHECK (purpose IN ('registration','login','reset'))"
    )
