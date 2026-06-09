"""add bvn_lookup to user_pii (deterministic dedup hash)

Revision ID: 0003_add_bvn_lookup
Revises: 0002_create_auth_credentials
Create Date: 2026-06-09

bvn_hash is bcrypt (salted, per-row) so it can verify a BVN but cannot be
queried. bvn_lookup is an HMAC-SHA256(bvn, server pepper) — deterministic,
so a UNIQUE index enforces one-BVN-one-account (AML/KYC dedup). The pepper
is a server secret; the column never holds a reversible value.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_add_bvn_lookup"
down_revision: str | None = "0002_create_auth_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # HMAC-SHA256 hex digest is 64 chars.
    op.execute("ALTER TABLE user_pii ADD COLUMN bvn_lookup VARCHAR(64)")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_bvn_lookup "
        "ON user_pii(bvn_lookup) WHERE bvn_lookup IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_pii_bvn_lookup")
    op.execute("ALTER TABLE user_pii DROP COLUMN IF EXISTS bvn_lookup")
