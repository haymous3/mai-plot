"""create listing tables: property_listings (partitioned), listing_media, offers

Revision ID: 0001_create_listing_tables
Revises:
Create Date: 2026-05-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_listing_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Eight quarterly partitions seed the table for two years of dev usage.
# Production gets pg_partman in a later ticket (out of M0 scope) which
# auto-creates ahead-of-time partitions on a rolling window.
_QUARTERS = [
    ("2026_q1", "2026-01-01", "2026-04-01"),
    ("2026_q2", "2026-04-01", "2026-07-01"),
    ("2026_q3", "2026-07-01", "2026-10-01"),
    ("2026_q4", "2026-10-01", "2027-01-01"),
    ("2027_q1", "2027-01-01", "2027-04-01"),
    ("2027_q2", "2027-04-01", "2027-07-01"),
    ("2027_q3", "2027-07-01", "2027-10-01"),
    ("2027_q4", "2027-10-01", "2028-01-01"),
]


def upgrade() -> None:
    # PostGIS supplies the GEOGRAPHY type used by property_listings.location.
    # Locally it arrives via infra/docker/postgres/init.sql, but managed
    # providers (Render, RDS) have no init-script hook — so the migration
    # bootstraps it. IF NOT EXISTS keeps this a no-op where init.sql ran.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # property_listings — partitioned by created_at so query planner only
    # scans the relevant slice. Composite primary key is required for range
    # partitioning. PostGIS GEOGRAPHY column supports the GIST geo index.
    op.execute(
        """
        CREATE TABLE property_listings (
            id                      UUID NOT NULL DEFAULT gen_random_uuid(),
            seller_id               UUID NOT NULL REFERENCES users(id),
            property_type           VARCHAR(20) NOT NULL
                                    CHECK (property_type IN ('land','residential','commercial')),
            title                   VARCHAR(300) NOT NULL,
            description             TEXT,
            address_text            TEXT NOT NULL,
            location                GEOGRAPHY(POINT, 4326) NOT NULL,
            lga                     VARCHAR(100) NOT NULL,
            state                   VARCHAR(50)  NOT NULL,
            size_sqm                NUMERIC(12,2),
            asking_price_kobo       BIGINT NOT NULL CHECK (asking_price_kobo > 0),
            sale_type               VARCHAR(20) NOT NULL CHECK (sale_type IN ('distress','normal')),
            urgency_tag             VARCHAR(10) CHECK (
                                        (sale_type = 'distress' AND urgency_tag IN ('7_days','14_days','30_days'))
                                        OR (sale_type = 'normal' AND urgency_tag IS NULL)
                                    ),
            status                  VARCHAR(30) NOT NULL DEFAULT 'pending_review'
                                    CHECK (status IN ('pending_review','active','under_offer','sold','expired','rejected')),
            doc_verification_status VARCHAR(20) NOT NULL DEFAULT 'not_submitted'
                                    CHECK (doc_verification_status IN ('not_submitted','pending','verified','failed')),
            rejection_reason        TEXT,
            view_count              INTEGER NOT NULL DEFAULT 0,
            interest_count          INTEGER NOT NULL DEFAULT 0,
            expires_at              TIMESTAMPTZ,
            es_indexed_at           TIMESTAMPTZ,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at              TIMESTAMPTZ,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """
    )

    for name, start, end in _QUARTERS:
        op.execute(
            f"CREATE TABLE property_listings_{name} "
            f"PARTITION OF property_listings "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )

    op.execute("CREATE INDEX idx_listings_seller       ON property_listings(seller_id, status)")
    op.execute(
        "CREATE INDEX idx_listings_state_status ON property_listings(state, status, asking_price_kobo)"
    )
    op.execute(
        "CREATE INDEX idx_listings_sale_type    ON property_listings(sale_type, status, expires_at)"
    )
    op.execute("CREATE INDEX idx_listings_location     ON property_listings USING GIST(location)")

    # listing_media — soft FK to listing_id (no constraint because the
    # parent is partitioned and the composite PK makes a normal FK awkward).
    # Application layer guarantees referential integrity.
    op.execute(
        """
        CREATE TABLE listing_media (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_id UUID NOT NULL,
            media_type VARCHAR(10) NOT NULL CHECK (media_type IN ('photo','video')),
            s3_key     TEXT NOT NULL,
            cdn_url    TEXT NOT NULL,
            sort_order SMALLINT NOT NULL DEFAULT 0,
            size_bytes INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_media_listing ON listing_media(listing_id, sort_order)")

    # offers — buyer offers before acceptance. listing_id is a soft FK for
    # the same reason as listing_media.
    op.execute(
        """
        CREATE TABLE offers (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_id         UUID NOT NULL,
            buyer_id           UUID NOT NULL REFERENCES users(id),
            offered_price_kobo BIGINT NOT NULL CHECK (offered_price_kobo > 0),
            note               TEXT,
            status             VARCHAR(20) NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending','accepted','rejected','countered','withdrawn')),
            counter_price_kobo BIGINT,
            expires_at         TIMESTAMPTZ NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_offers_listing ON offers(listing_id, status)")
    op.execute("CREATE INDEX idx_offers_buyer   ON offers(buyer_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS offers CASCADE")
    op.execute("DROP TABLE IF EXISTS listing_media CASCADE")
    for name, _, _ in reversed(_QUARTERS):
        op.execute(f"DROP TABLE IF EXISTS property_listings_{name} CASCADE")
    op.execute("DROP TABLE IF EXISTS property_listings CASCADE")
