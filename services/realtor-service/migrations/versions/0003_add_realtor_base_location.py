"""add base_location to realtors (SCRUM-72)

The auto-assignment algorithm picks the nearest approved realtor to a property by
PostGIS distance, so a realtor needs a geolocation. base_location is the realtor's
base point (captured at registration); realtors without one are not assignable.
Non-§11 table.

Revision ID: 0003_realtor_base_location
Revises: 0002_realtor_government_id
Create Date: 2026-06-24

(Revision id kept <= 32 chars for the alembic_version column.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_realtor_base_location"
down_revision: str | None = "0002_realtor_government_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE realtors ADD COLUMN base_location GEOGRAPHY(POINT, 4326)")
    op.execute("CREATE INDEX idx_realtors_base_location ON realtors USING GIST(base_location)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_realtors_base_location")
    op.execute("ALTER TABLE realtors DROP COLUMN IF EXISTS base_location")
