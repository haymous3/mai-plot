"""create document tables: listing_documents

Revision ID: 0001_create_document_tables
Revises:
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_create_document_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # listing_documents — title docs, OCR output, verification workflow.
    # listing_id is a soft FK because property_listings is partitioned and
    # the composite PK doesn't accept a regular FK. verified_by_user_id
    # references users so the document service must run after auth.
    op.execute(
        """
        CREATE TABLE listing_documents (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_id          UUID NOT NULL,
            document_type       VARCHAR(50) NOT NULL
                                CHECK (document_type IN (
                                    'c_of_o','deed_of_assignment','survey_plan',
                                    'governors_consent','receipt','poa','other'
                                )),
            s3_key              TEXT NOT NULL,
            ocr_extracted_data  JSONB,
            verification_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (verification_status IN ('pending','verified','failed','under_review')),
            verified_by_user_id UUID REFERENCES users(id),
            verification_notes  TEXT,
            watermark_applied   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_docs_listing ON listing_documents(listing_id, verification_status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS listing_documents CASCADE")
