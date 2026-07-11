"""create payout_accounts (SCRUM-145)

Payee (realtor / seller) bank details for real Paystack transfers: the NUBAN
account plus its Paystack transfer recipient_code. This is where a payout is sent
— it stores no balances and moves no money, so it is NOT a §11 table (not
users / transactions / escrow_ledger). account_number is financial PII: keep it
out of logs and API responses (masked to the last 4 digits at the edge).

Revision ID: 0002_create_payout_accounts
Revises: 0001_create_transaction_tables
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_payout_accounts"
down_revision: str | None = "0001_create_transaction_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One payout account per user (user_id UNIQUE). recipient_code is filled once
    # Paystack's transfer recipient is created for the account (nullable until
    # then). deleted_at kept for the soft-delete convention (CLAUDE.md).
    op.execute(
        """
        CREATE TABLE payout_accounts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL UNIQUE REFERENCES users(id),
            account_number  VARCHAR(20) NOT NULL,
            bank_code       VARCHAR(10) NOT NULL,
            account_name    TEXT NOT NULL,
            recipient_code  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at      TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payout_accounts CASCADE")
