"""create realtor tables: realtors, inspections (FK transactions added later)

Revision ID: 0001_create_realtor_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_realtor_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # realtors — extends users with ESVARBON licence and coverage area arrays.
    op.execute(
        """
        CREATE TABLE realtors (
            id                  UUID PRIMARY KEY REFERENCES users(id),
            esvarbon_number     VARCHAR(100) UNIQUE,
            years_of_experience SMALLINT,
            coverage_states     VARCHAR(50)[] NOT NULL DEFAULT '{}',
            coverage_lgas       TEXT[]        NOT NULL DEFAULT '{}',
            completed_deals     INTEGER NOT NULL DEFAULT 0,
            approval_status     VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (approval_status IN ('pending','approved','suspended','rejected')),
            approved_by         UUID REFERENCES users(id),
            approved_at         TIMESTAMPTZ,
            suspension_reason   TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # inspections — transaction_id FK is added in transaction-service's
    # initial migration after the transactions table exists. Until then the
    # column carries no constraint, only a logical reference.
    op.execute(
        """
        CREATE TABLE inspections (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id        UUID NOT NULL,
            realtor_id            UUID NOT NULL REFERENCES users(id),
            proposed_date         TIMESTAMPTZ NOT NULL,
            confirmed_date        TIMESTAMPTZ,
            status                VARCHAR(20) NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','accepted','rescheduled','completed','no_show')),
            gps_lat               NUMERIC(9,6),
            gps_lng               NUMERIC(9,6),
            report_submitted_at   TIMESTAMPTZ,
            report_data           JSONB,
            assignment_expires_at TIMESTAMPTZ NOT NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_inspections_realtor ON inspections(realtor_id, status)")
    op.execute("CREATE INDEX idx_inspections_txn     ON inspections(transaction_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inspections CASCADE")
    op.execute("DROP TABLE IF EXISTS realtors CASCADE")
