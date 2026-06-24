"""add government_id_s3_key to realtors (SCRUM-71)

The realtor's government-ID document is stored in the PRIVATE documents bucket;
this column holds its S3 key (the bytes are never in the DB). Non-§11 table.

Revision ID: 0002_realtor_government_id
Revises: 0001_create_realtor_tables
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_realtor_government_id"
down_revision: str | None = "0001_create_realtor_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE realtors ADD COLUMN government_id_s3_key VARCHAR(512)")


def downgrade() -> None:
    op.execute("ALTER TABLE realtors DROP COLUMN IF EXISTS government_id_s3_key")
