"""create analytics tables: audit_log + append-only trigger

Revision ID: 0001_create_analytics_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_analytics_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # audit_log — INSERT-only audit trail across every entity. The
    # BEFORE UPDATE/DELETE trigger below is the DB-level guarantee; the
    # service layer also blocks these operations, but the trigger is the
    # last line of defense.
    op.execute(
        """
        CREATE TABLE audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id    UUID REFERENCES users(id),
            actor_role  VARCHAR(20),
            action      VARCHAR(100) NOT NULL,
            entity_type VARCHAR(50)  NOT NULL,
            entity_id   UUID,
            old_value   JSONB,
            new_value   JSONB,
            ip_address  INET,
            user_agent  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id, created_at DESC)")
    op.execute("CREATE INDEX idx_audit_actor  ON audit_log(actor_id, created_at DESC)")

    # Append-only enforcement. Raising an exception from a BEFORE trigger
    # aborts the statement; the row is never modified or deleted.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_no_modify() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; % not permitted', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_update "
        "BEFORE UPDATE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_delete "
        "BEFORE DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_modify()")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
