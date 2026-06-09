"""create auth_credentials table (password login)

Revision ID: 0002_create_auth_credentials
Revises: 0001_create_auth_tables
Create Date: 2026-06-09

A dedicated credential table keeps the password hash out of the core
`users` row (which is cacheable identity data) and out of `user_pii`
(KMS-encrypted regulated PII). bcrypt hashes are not reversible secrets
in the PII sense, so they live in their own table that can grow
password-reset / rotation columns later without touching users.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_auth_credentials"
down_revision: str | None = "0001_create_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # password_hash is bcrypt ($2b$… = 60 chars); VARCHAR(128) matches the
    # other hash columns in this schema (code_hash, bvn_hash).
    op.execute(
        """
        CREATE TABLE auth_credentials (
            user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            password_hash VARCHAR(128) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_credentials CASCADE")
