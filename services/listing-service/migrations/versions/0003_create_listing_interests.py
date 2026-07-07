"""create listing_interests table (buyer "Express Interest")

Revision ID: 0003_create_listing_interests
Revises: 0002_create_saved_listings
Create Date: 2026-07-07

Records a buyer expressing interest in a listing (SCRUM-95) — lighter than an
offer. One row per (buyer, listing) so a repeat click does not double-count;
the listing's interest_count is incremented only on the first interest. buyer_id
FKs users (like property_listings.seller_id); listing_id is a plain UUID
(property_listings has a partitioned composite PK — cannot be an FK target).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_create_listing_interests"
down_revision: str | None = "0002_create_saved_listings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE listing_interests (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            buyer_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_id  UUID NOT NULL,
            message     TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ,
            UNIQUE (buyer_id, listing_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_listing_interests_listing ON listing_interests(listing_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS listing_interests CASCADE")
