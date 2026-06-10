"""add nin_lookup to user_pii (deterministic dedup hash)

Revision ID: 0004_add_nin_lookup
Revises: 0003_add_bvn_lookup
Create Date: 2026-06-09

Mirrors 0003 (bvn_lookup): nin_hash is bcrypt (salted, verify-only);
nin_lookup is HMAC-SHA256(nin, NIN_PEPPER), deterministic, with a UNIQUE
index enforcing one-NIN-one-account.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_add_nin_lookup"
down_revision: str | None = "0003_add_bvn_lookup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_pii ADD COLUMN nin_lookup VARCHAR(64)")
    op.execute(
        "CREATE UNIQUE INDEX idx_user_pii_nin_lookup "
        "ON user_pii(nin_lookup) WHERE nin_lookup IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_pii_nin_lookup")
    op.execute("ALTER TABLE user_pii DROP COLUMN IF EXISTS nin_lookup")
