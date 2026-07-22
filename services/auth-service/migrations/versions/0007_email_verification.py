"""create email_verification_tokens + allow users.verified_status = 'email_verified'

Revision ID: 0007_email_verification
Revises: 0006_create_buyer_profiles
Create Date: 2026-07-22

SCRUM-152 — account verification moves from phone-OTP-over-SMS to an email
magic link. This migration:

  * creates email_verification_tokens — one row per issued link. The token
    itself is never stored; only its SHA-256 hash. A magic-link token is a
    256-bit random value (secrets.token_urlsafe(32)), so it is NOT brute-
    forceable the way the 6-digit OTP is — SHA-256 (fast, indexable) is the
    right choice here, whereas the OTP stays bcrypt. Single-use via used_at.

  * widens the users.verified_status CHECK constraint to admit
    'email_verified' (§11 users-table change, signed off for this ticket).

The otp_codes table and the phone-OTP verify path are left intact — the
endpoint stays live but registration no longer emits OTPs.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_email_verification"
down_revision: str | None = "0006_create_buyer_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# asyncpg refuses multi-statement strings, so every DDL statement is its own
# op.execute() call (see the note in 0001).


def upgrade() -> None:
    # token_hash is a SHA-256 hex digest = 64 chars. The UNIQUE index doubles
    # as the lookup index for verification (find-by-hash); a 256-bit token
    # makes collisions effectively impossible, so uniqueness is free insurance.
    op.execute(
        """
        CREATE TABLE email_verification_tokens (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            email      VARCHAR(254) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            purpose    VARCHAR(30) NOT NULL
                       CHECK (purpose IN ('registration','login','reset')),
            used_at    TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX idx_evt_token_hash ON email_verification_tokens(token_hash)")
    op.execute(
        "CREATE INDEX idx_evt_user_purpose ON email_verification_tokens(user_id, purpose) "
        "WHERE used_at IS NULL"
    )

    # Widen the verified_status domain to include 'email_verified'. The inline
    # CHECK from 0001 is auto-named users_verified_status_check by Postgres.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_verified_status_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_verified_status_check "
        "CHECK (verified_status IN "
        "('unverified','phone_verified','email_verified','id_verified','fully_verified'))"
    )


def downgrade() -> None:
    # Revert the constraint first (rows still on 'email_verified' would violate
    # the narrowed CHECK, so fold them back to 'unverified' before re-adding it).
    op.execute(
        "UPDATE users SET verified_status = 'unverified' WHERE verified_status = 'email_verified'"
    )
    op.execute("ALTER TABLE users DROP CONSTRAINT users_verified_status_check")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_verified_status_check "
        "CHECK (verified_status IN "
        "('unverified','phone_verified','id_verified','fully_verified'))"
    )
    op.execute("DROP TABLE IF EXISTS email_verification_tokens CASCADE")
