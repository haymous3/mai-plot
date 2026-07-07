"""add 'paused' to property_listings.status

Revision ID: 0004_add_paused_status
Revises: 0003_create_listing_interests
Create Date: 2026-07-07

Sellers can pause/resume a live listing from "My Listings" (SCRUM-98). A paused
listing is hidden from the buyer feed but not deleted. Extends the status CHECK.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_add_paused_status"
down_revision: str | None = "0003_create_listing_interests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE property_listings DROP CONSTRAINT property_listings_status_check")
    op.execute(
        """
        ALTER TABLE property_listings ADD CONSTRAINT property_listings_status_check
        CHECK (status IN ('pending_review','active','under_offer','sold','expired','rejected','paused'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE property_listings DROP CONSTRAINT property_listings_status_check")
    op.execute(
        """
        ALTER TABLE property_listings ADD CONSTRAINT property_listings_status_check
        CHECK (status IN ('pending_review','active','under_offer','sold','expired','rejected'))
        """
    )
