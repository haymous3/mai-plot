"""add property_listings.search_vector for Postgres full-text search

Revision ID: 0006_add_listing_search_vector
Revises: 0005_add_expired_offer_status
Create Date: 2026-10-21

SCRUM-251 moves GET /listings/search off Elasticsearch onto Postgres. The
document is a GENERATED column, so it can never drift from the row it is
computed from — the drift class SCRUM-215 hit (a paused listing still
searchable because its ES copy still said "active") cannot happen. Title is
weight A, everything else weight B, matching the old multi_match `title^2`.

The two-argument to_tsvector with a constant regconfig is IMMUTABLE, which a
generated column requires. Adding the column to the partitioned parent adds it
to every partition; the GIN index on the parent likewise cascades. The table
is small, so a plain (non-concurrent) build is fine — and CONCURRENTLY is not
supported on a partitioned parent anyway.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_add_listing_search_vector"
down_revision: str | None = "0005_add_expired_offer_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE property_listings ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A')
            || setweight(
                to_tsvector(
                    'english',
                    coalesce(description, '') || ' ' || coalesce(address_text, '') || ' '
                    || coalesce(lga, '') || ' ' || coalesce(state, '')
                ),
                'B'
            )
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_listings_search_vector ON property_listings USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_listings_search_vector")
    op.execute("ALTER TABLE property_listings DROP COLUMN IF EXISTS search_vector")
