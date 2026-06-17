"""create offers table (SCRUM-66)

The pre-transaction offer/negotiation. Separate from `transactions` (which
starts at 'offer_accepted'): an accepted offer creates a transactions row.
New table — does NOT touch transactions/escrow_ledger/users (no §11 change).

Revision ID: 0002_create_offers
Revises: 0001_create_transaction_tables
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_offers"
down_revision: str | None = "0001_create_transaction_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE offers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_id          UUID NOT NULL,
            buyer_id            UUID NOT NULL REFERENCES users(id),
            seller_id           UUID NOT NULL REFERENCES users(id),
            amount_kobo         BIGINT NOT NULL CHECK (amount_kobo > 0),
            counter_amount_kobo BIGINT CHECK (counter_amount_kobo > 0),
            status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending','countered','accepted','rejected','expired','withdrawn'
                                )),
            transaction_id      UUID REFERENCES transactions(id),
            expires_at          TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_offers_listing ON offers(listing_id, status)")
    op.execute("CREATE INDEX idx_offers_buyer ON offers(buyer_id, status)")
    op.execute("CREATE INDEX idx_offers_seller ON offers(seller_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS offers CASCADE")
