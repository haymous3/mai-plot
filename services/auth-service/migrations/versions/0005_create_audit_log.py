"""create audit_log (append-only system audit trail)

Revision ID: 0005_create_audit_log
Revises: 0004_add_nin_lookup
Create Date: 2026-06-10

Append-only audit trail per data-model.md §19. SCRUM-48 writes the first
rows (poa.uploaded) so PoA document handling is fully traceable. INSERT-only
by convention — the service layer never updates or deletes audit rows.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_create_audit_log"
down_revision: str | None = "0004_add_nin_lookup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id    UUID REFERENCES users(id),
            actor_role  VARCHAR(20),
            action      VARCHAR(100) NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            entity_id   UUID,
            old_value   JSONB,
            new_value   JSONB,
            ip_address  INET,
            user_agent  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id, created_at DESC)"
    )
    op.execute("CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
