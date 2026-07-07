"""create buyer_profiles table (buyer onboarding "Personal Information")

Revision ID: 0006_create_buyer_profiles
Revises: 0005_add_legal_team_role
Create Date: 2026-07-07

Holds the optional "buying capacity" fields captured on the buyer onboarding
screen (SCRUM-132): employment status, preferred location, and budget. Kept in
its own table rather than on `users` so the core identity row stays cache-safe
and this can grow without a users migration. budget_kobo is BIGINT kobo per the
money rule. One row per buyer (user_id unique).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_create_buyer_profiles"
down_revision: str | None = "0005_add_legal_team_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE buyer_profiles (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            employment_status  VARCHAR(30),
            preferred_location VARCHAR(120),
            budget_kobo        BIGINT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at         TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS buyer_profiles CASCADE")
