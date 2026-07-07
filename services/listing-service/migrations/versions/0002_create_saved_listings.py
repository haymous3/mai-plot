"""create saved_listings table (buyer favourites)

Revision ID: 0002_create_saved_listings
Revises: 0001_create_listing_tables
Create Date: 2026-07-07

Buyer "save/favourite" relationship for the dashboard hearts + Saved Properties
card (SCRUM-95). One row per (buyer, listing); a re-save clears deleted_at
(soft-delete toggle) so the unique constraint holds across unsave/re-save.
buyer_id FKs users (consistent with property_listings.seller_id); listing_id is
a plain UUID because property_listings has a partitioned composite PK and cannot
be the target of a foreign key.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_saved_listings"
down_revision: str | None = "0001_create_listing_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE saved_listings (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            buyer_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_id  UUID NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ,
            UNIQUE (buyer_id, listing_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_saved_listings_buyer ON saved_listings(buyer_id) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_listings CASCADE")
