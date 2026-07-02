"""create loan_documents (buyer loan-application documents, SCRUM-131)

The buyer onboarding wizard (SCRUM-94) collects a bank statement, an employment
letter/CAC doc, and a passport photo, but the only upload table was
listing_documents (seller-scoped). loan_documents is the buyer/loan equivalent:
private-bucket files served only via short-TTL pre-signed URLs. loan_id is a soft
FK (loans lives in loan-service's schema); uploaded_by references users.

Revision ID: 0002_create_loan_documents
Revises: 0001_create_document_tables
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_create_loan_documents"
down_revision: str | None = "0001_create_document_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE loan_documents (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_id             UUID NOT NULL,
            document_type       VARCHAR(50) NOT NULL
                                CHECK (document_type IN (
                                    'bank_statement','employment_letter','passport'
                                )),
            s3_key              TEXT NOT NULL,
            verification_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (verification_status IN
                                    ('pending','verified','failed','under_review')),
            uploaded_by_user_id UUID REFERENCES users(id),
            verification_notes  TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_loan_docs_loan ON loan_documents(loan_id, verification_status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS loan_documents CASCADE")
