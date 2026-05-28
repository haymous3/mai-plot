"""create loan tables: bank_partners, loans (FK transactions added later), loan_repayment_milestones

Revision ID: 0001_create_loan_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_loan_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # bank_partners — reference data for partner bank configuration.
    # api_base_url is stored here for documentation only; actual API
    # credentials live in AWS Secrets Manager.
    op.execute(
        """
        CREATE TABLE bank_partners (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                     VARCHAR(200) NOT NULL,
            short_code               VARCHAR(20) NOT NULL UNIQUE,
            api_base_url             TEXT,
            loan_min_kobo            BIGINT  NOT NULL,
            loan_max_kobo            BIGINT  NOT NULL,
            interest_rate_bps        INTEGER NOT NULL,
            min_tenure_months        SMALLINT NOT NULL,
            max_tenure_months        SMALLINT NOT NULL,
            requires_account_opening BOOLEAN NOT NULL DEFAULT TRUE,
            is_active                BOOLEAN NOT NULL DEFAULT TRUE,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # loans — buyer-facing loan applications. transaction_id is a soft FK
    # for now; the constraint is added in transaction-service's initial
    # migration after the transactions table exists.
    op.execute(
        """
        CREATE TABLE loans (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_id          UUID NOT NULL,
            buyer_id                UUID NOT NULL REFERENCES users(id),
            bank_partner_id         UUID NOT NULL REFERENCES bank_partners(id),
            requested_amount_kobo   BIGINT NOT NULL,
            approved_amount_kobo    BIGINT,
            interest_rate_bps       INTEGER,
            tenure_months           SMALLINT,
            monthly_instalment_kobo BIGINT,
            status                  VARCHAR(30) NOT NULL DEFAULT 'submitted'
                                    CHECK (status IN (
                                        'submitted','under_review','approved',
                                        'rejected','info_required','disbursed',
                                        'repaying','fully_repaid','defaulted'
                                    )),
            bank_reference_id       VARCHAR(200),
            bank_decision_at        TIMESTAMPTZ,
            bank_account_opened     BOOLEAN NOT NULL DEFAULT FALSE,
            title_released_at       TIMESTAMPTZ,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_loans_buyer ON loans(buyer_id, status)")
    op.execute("CREATE INDEX idx_loans_txn   ON loans(transaction_id)")

    # loan_repayment_milestones — tracks installments and bank webhook updates.
    op.execute(
        """
        CREATE TABLE loan_repayment_milestones (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_id          UUID NOT NULL REFERENCES loans(id),
            due_date         DATE NOT NULL,
            amount_due_kobo  BIGINT NOT NULL,
            amount_paid_kobo BIGINT NOT NULL DEFAULT 0,
            status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending','paid','overdue')),
            paid_at          TIMESTAMPTZ,
            bank_reference   VARCHAR(200),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_repayments_loan ON loan_repayment_milestones(loan_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS loan_repayment_milestones CASCADE")
    op.execute("DROP TABLE IF EXISTS loans CASCADE")
    op.execute("DROP TABLE IF EXISTS bank_partners CASCADE")
