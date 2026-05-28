"""create transaction tables + close cross-service FKs

transactions, transaction_events, payment_events, escrow_ledger. Also
back-fills the deferred FKs from inspections.transaction_id and
loans.transaction_id, which were created as bare UUID columns by
realtor-service and loan-service before transactions existed.

Revision ID: 0001_create_transaction_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_transaction_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # transactions — current-state projection. transaction_events is the
    # event-sourced source of truth; this table holds the latest stage so
    # reads stay cheap. State machine enforcement lives in the service layer.
    op.execute(
        """
        CREATE TABLE transactions (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_id        UUID NOT NULL,
            buyer_id          UUID NOT NULL REFERENCES users(id),
            seller_id         UUID NOT NULL REFERENCES users(id),
            realtor_id        UUID REFERENCES users(id),
            agreed_price_kobo BIGINT NOT NULL CHECK (agreed_price_kobo > 0),
            platform_fee_kobo BIGINT,
            loan_id           UUID,
            stage             VARCHAR(30) NOT NULL DEFAULT 'offer_accepted'
                              CHECK (stage IN (
                                  'offer_accepted','inspection_scheduled','inspection_completed',
                                  'loan_applied','loan_approved','loan_rejected',
                                  'payment_held','title_held','completed',
                                  'cancelled','disputed','resolved'
                              )),
            lock_expires_at   TIMESTAMPTZ,
            dispute_reason    TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_txn_buyer   ON transactions(buyer_id, stage)")
    op.execute("CREATE INDEX idx_txn_seller  ON transactions(seller_id, stage)")
    op.execute("CREATE INDEX idx_txn_listing ON transactions(listing_id)")

    # transaction_events — append-only event log. No updated_at / deleted_at.
    # Service-layer code refuses UPDATE/DELETE; a future ticket may add a
    # trigger here too (similar to audit_log in analytics-service).
    op.execute(
        """
        CREATE TABLE transaction_events (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id UUID NOT NULL REFERENCES transactions(id),
            event_type     VARCHAR(50) NOT NULL,
            from_stage     VARCHAR(30),
            to_stage       VARCHAR(30) NOT NULL,
            triggered_by   UUID REFERENCES users(id),
            metadata       JSONB,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_txn_events_txn ON transaction_events(transaction_id, created_at)"
    )

    # payment_events — idempotent payment record. UNIQUE(payer_id,
    # idempotency_key) is the last line of defense against duplicate
    # Paystack webhook delivery (CLAUDE.md non-negotiable).
    op.execute(
        """
        CREATE TABLE payment_events (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            idempotency_key    UUID NOT NULL,
            payer_id           UUID NOT NULL REFERENCES users(id),
            payee_id           UUID REFERENCES users(id),
            transaction_id     UUID REFERENCES transactions(id),
            amount_kobo        BIGINT NOT NULL CHECK (amount_kobo > 0),
            payment_type       VARCHAR(30) NOT NULL
                               CHECK (payment_type IN (
                                   'buyer_deposit','escrow_hold','seller_disbursement',
                                   'realtor_commission','platform_fee','loan_disbursement','refund'
                               )),
            provider           VARCHAR(20) NOT NULL CHECK (provider IN ('paystack','flutterwave','bank_transfer')),
            provider_reference VARCHAR(200),
            status             VARCHAR(20) NOT NULL DEFAULT 'initiated'
                               CHECK (status IN ('initiated','processing','completed','failed','refunded')),
            metadata           JSONB,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (payer_id, idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX idx_payment_txn ON payment_events(transaction_id, payment_type)")
    op.execute(
        "CREATE INDEX idx_payment_provider_ref ON payment_events(provider_reference) "
        "WHERE provider_reference IS NOT NULL"
    )

    # escrow_ledger — double-entry append-only ledger. Dual approval gate
    # (requires_dual_approval / approved_by_2) enforced in service layer
    # when amount_kobo > 1,000,000,000 per CLAUDE.md rule.
    op.execute(
        """
        CREATE TABLE escrow_ledger (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id         UUID NOT NULL REFERENCES transactions(id),
            entry_type             VARCHAR(10) NOT NULL CHECK (entry_type IN ('credit','debit')),
            amount_kobo            BIGINT NOT NULL CHECK (amount_kobo > 0),
            description            VARCHAR(300) NOT NULL,
            payment_event_id       UUID REFERENCES payment_events(id),
            requires_dual_approval BOOLEAN NOT NULL DEFAULT FALSE,
            approved_by_1          UUID REFERENCES users(id),
            approved_by_2          UUID REFERENCES users(id),
            approved_at            TIMESTAMPTZ,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_escrow_txn ON escrow_ledger(transaction_id, created_at)")

    # Close the deferred cross-service FKs. inspections and loans were
    # created earlier with bare UUID transaction_id columns because
    # transactions did not exist yet. Now that it does, add the constraints.
    op.execute(
        "ALTER TABLE inspections "
        "ADD CONSTRAINT fk_inspections_transaction "
        "FOREIGN KEY (transaction_id) REFERENCES transactions(id)"
    )
    op.execute(
        "ALTER TABLE loans "
        "ADD CONSTRAINT fk_loans_transaction "
        "FOREIGN KEY (transaction_id) REFERENCES transactions(id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE loans DROP CONSTRAINT IF EXISTS fk_loans_transaction")
    op.execute("ALTER TABLE inspections DROP CONSTRAINT IF EXISTS fk_inspections_transaction")
    op.execute("DROP TABLE IF EXISTS escrow_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS payment_events CASCADE")
    op.execute("DROP TABLE IF EXISTS transaction_events CASCADE")
    op.execute("DROP TABLE IF EXISTS transactions CASCADE")
