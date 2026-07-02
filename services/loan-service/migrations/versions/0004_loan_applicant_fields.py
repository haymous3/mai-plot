"""loan applicant fields: employment_status + monthly_income_kobo (SCRUM-131)

The buyer onboarding wizard (SCRUM-94) collects employment status and monthly
income but had nowhere to store them. Add two nullable columns to loans so the
application persists them for the reviewing bank. Non-§11 (loans is loan-service's
own table, not users/transactions/escrow_ledger). Money is BIGINT kobo per §4.

Revision ID: 0004_loan_applicant_fields
Revises: 0003_repayment_milestone_keys
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_loan_applicant_fields"
down_revision: str | None = "0003_repayment_milestone_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE loans ADD COLUMN employment_status VARCHAR(30)")
    op.execute("ALTER TABLE loans ADD COLUMN monthly_income_kobo BIGINT")


def downgrade() -> None:
    op.execute("ALTER TABLE loans DROP COLUMN IF EXISTS monthly_income_kobo")
    op.execute("ALTER TABLE loans DROP COLUMN IF EXISTS employment_status")
