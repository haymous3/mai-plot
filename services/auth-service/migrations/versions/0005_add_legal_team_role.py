"""add 'legal_team' to the users.role CHECK constraint (SCRUM-56)

Revision ID: 0005_add_legal_team_role
Revises: 0004_add_nin_lookup
Create Date: 2026-06-15

The PoA review queue is gated to a dedicated `legal_team` role (separate from
general `admin`). The role column carries an inline CHECK constraint
(auto-named users_role_check by Postgres); this drops and re-adds it with the
new value. Additive + reversible. (Human-approved per CLAUDE.md §11 — a schema
change on the users table.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_add_legal_team_role"
down_revision: str | None = "0004_add_nin_lookup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES_WITH = "'seller','buyer','realtor','bank_partner','admin','legal_team'"
_ROLES_WITHOUT = "'seller','buyer','realtor','bank_partner','admin'"


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT users_role_check")
    op.execute(f"ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({_ROLES_WITH}))")


def downgrade() -> None:
    # Reversible only if no legal_team rows exist (the CHECK would reject them).
    op.execute("ALTER TABLE users DROP CONSTRAINT users_role_check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({_ROLES_WITHOUT}))"
    )
