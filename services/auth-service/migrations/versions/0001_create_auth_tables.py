"""create auth tables: users, user_pii, otp_codes, refresh_tokens

Revision ID: 0001_create_auth_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_auth_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# asyncpg's prepared-statement execution refuses multi-statement strings,
# so every CREATE TABLE / CREATE INDEX / ALTER is its own op.execute() call.


def upgrade() -> None:
    # users — core identity, safe to cache. PII lives in user_pii.
    op.execute(
        """
        CREATE TABLE users (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            role                  VARCHAR(20) NOT NULL
                                  CHECK (role IN ('seller','buyer','realtor','bank_partner','admin')),
            email                 VARCHAR(254) UNIQUE,
            verified_status       VARCHAR(30) NOT NULL DEFAULT 'unverified'
                                  CHECK (verified_status IN ('unverified','phone_verified','id_verified','fully_verified')),
            seller_authority_type VARCHAR(30)
                                  CHECK (seller_authority_type IN ('owner','power_of_attorney')),
            poa_verified_status   VARCHAR(20) DEFAULT 'not_applicable'
                                  CHECK (poa_verified_status IN ('not_applicable','pending','verified','rejected')),
            is_active             BOOLEAN NOT NULL DEFAULT TRUE,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at            TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_users_role  ON users(role)  WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX idx_users_email ON users(email) WHERE email IS NOT NULL")

    # user_pii — sensitive fields, never cached. bcrypt hashes for BVN/NIN.
    op.execute(
        """
        CREATE TABLE user_pii (
            user_id                 UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            phone                   VARCHAR(20) UNIQUE NOT NULL,
            full_name               TEXT NOT NULL,
            bvn_hash                VARCHAR(128),
            nin_hash                VARCHAR(128),
            poa_document_s3_key     VARCHAR(512),
            poa_document_owner_name TEXT,
            employment_status       VARCHAR(30),
            monthly_income_kobo     BIGINT,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_user_pii_phone ON user_pii(phone)")

    # otp_codes — 6-digit single-use codes. 5-min TTL + Redis blacklist in
    # the service layer; code_hash is bcrypt to prevent rainbow-table lookup.
    op.execute(
        """
        CREATE TABLE otp_codes (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone      VARCHAR(20) NOT NULL,
            code_hash  VARCHAR(128) NOT NULL,
            purpose    VARCHAR(30) NOT NULL CHECK (purpose IN ('registration','login','reset')),
            used_at    TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_otp_phone_purpose ON otp_codes(phone, purpose) WHERE used_at IS NULL"
    )

    # refresh_tokens — long-lived JWT refresh credentials. Token never stored
    # in plaintext; only the hash. revoked_at supports instant invalidation.
    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES users(id),
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            device_id  VARCHAR(128),
            ip_address INET,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS otp_codes CASCADE")
    op.execute("DROP TABLE IF EXISTS user_pii CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
