"""add declined_realtor_ids to inspections (SCRUM-123)

When a realtor's 2-hour acceptance window lapses, the inspection is reassigned to
the next-nearest realtor — excluding everyone who already declined/lapsed. This
array records them so the reassignment sweep never re-offers it to the same
realtor. Non-§11 table.

Revision ID: 0005_inspection_declined
Revises: 0004_create_commissions
Create Date: 2026-06-24

(Revision id kept <= 32 chars for the alembic_version column.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_inspection_declined"
down_revision: str | None = "0004_create_commissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE inspections ADD COLUMN declined_realtor_ids UUID[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE inspections DROP COLUMN IF EXISTS declined_realtor_ids")
