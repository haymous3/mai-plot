"""record the verification channel and scope phone uniqueness to it

Revision ID: 0008_verification_channel
Revises: 0007_email_verification
Create Date: 2026-08-25

SCRUM-183 — a phone number may be reused by accounts that verify by EMAIL,
while remaining unique among accounts that verify by PHONE.

Why the column lives on user_pii and not users
----------------------------------------------
Semantically the channel belongs to the account, so `users` is the natural
home. It is on `user_pii` instead for one hard reason: PostgreSQL partial
indexes can only reference columns of their own table, and the uniqueness we
need to scope is on `user_pii.phone`. A column on `users` could not appear in
the index predicate. user_pii is 1:1 with users (shared PK), so there is no
denormalisation risk — just a column sitting next to the value it governs.

Why the phone constraint cannot simply be dropped
-------------------------------------------------
`get_by_phone()` decides WHOSE account an OTP verifies and receives JWTs for
(app/services/otp_verification.py). With an unscoped duplicate phone that
lookup is ambiguous, and could verify the wrong person. The partial unique
index makes the phone-channel set unique by construction, so the lookup — now
filtered to that same predicate — can match at most one row. The safety
property is enforced by the database, not by remembering to filter.

Backfill
--------
Existing rows are set to 'phone' unless already email_verified. That is
conservative and historically accurate: every account created under SCRUM-175
registered via OTP, and anything still `unverified` may yet verify by phone, so
it keeps its uniqueness protection. Accounts already `email_verified` release
their phone, which is precisely the new intended behaviour.

The backfill cannot violate the new index: the pre-existing constraint was
globally unique, so every phone is distinct before the narrowing.

§11: this is a schema change on the PII table adjacent to `users`, signed off
for this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_verification_channel"
down_revision: str | None = "0007_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DEFAULT 'email' matches the API default (SCRUM-180), so a row inserted by
    # an older code path lands in the non-unique set rather than silently
    # claiming a phone.
    op.execute("ALTER TABLE user_pii ADD COLUMN verification_channel VARCHAR(10) NOT NULL DEFAULT 'email'")
    op.execute(
        "ALTER TABLE user_pii ADD CONSTRAINT user_pii_verification_channel_check "
        "CHECK (verification_channel IN ('email','phone'))"
    )

    # Conservative backfill — see the module docstring.
    op.execute(
        """
        UPDATE user_pii SET verification_channel = 'phone'
        WHERE user_id IN (
            SELECT id FROM users WHERE verified_status IS DISTINCT FROM 'email_verified'
        )
        """
    )

    # Replace the global uniqueness with one scoped to the phone channel.
    # The constraint is the implicit one from `phone VARCHAR(20) UNIQUE` in
    # migration 0001; Postgres names it <table>_<column>_key.
    op.execute("ALTER TABLE user_pii DROP CONSTRAINT user_pii_phone_key")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_phone_channel_unique ON user_pii(phone) "
        "WHERE verification_channel = 'phone'"
    )


def downgrade() -> None:
    # Restoring the global constraint can FAIL, by design: if any phone was
    # reused by an email-channel account while this migration was applied, the
    # data no longer satisfies the old constraint. Failing loudly is correct —
    # silently deleting or merging accounts to force it through would be worse.
    op.execute("DROP INDEX IF EXISTS idx_user_pii_phone_channel_unique")
    op.execute("ALTER TABLE user_pii ADD CONSTRAINT user_pii_phone_key UNIQUE (phone)")
    op.execute("ALTER TABLE user_pii DROP CONSTRAINT user_pii_verification_channel_check")
    op.execute("ALTER TABLE user_pii DROP COLUMN verification_channel")
