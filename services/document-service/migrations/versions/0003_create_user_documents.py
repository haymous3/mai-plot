"""user-owned personal documents (My Documents)

Revision ID: 0003_create_user_documents
Revises: 0002_create_loan_documents
Create Date: 2026-08-27

SCRUM-188 — the Settings design ships a "My Documents" page where a user
uploads their own identity, financial and property paperwork. Neither existing
table can hold those rows:

  * `listing_documents.listing_id` is NOT NULL — a buyer has no listing, so
    they cannot own a row at all.
  * `loan_documents.loan_id`      is NOT NULL — those are application documents
    scoped to one loan, discarded reasoning-wise once it closes, and typed to
    just bank_statement / employment_letter / passport.

A personal document outlives both: it belongs to the PERSON, is uploaded before
any listing or loan exists, and is what the user expects to find again later.
Hence its own table rather than making an existing FK nullable — a nullable
listing_id would silently widen every existing listing-document query.

Status vocabulary
-----------------
Deliberately REUSES the vocabulary the other two document tables already use
(`pending` / `verified` / `failed` / `under_review`) instead of inventing
'rejected'. The design's pill reads "Rejected"; that is a LABEL for `failed`,
applied in the UI. Three document tables answering the same question with three
different words would be a reporting problem later, and the admin review
workflow (PR 5) can then treat all three alike.

Columns the other tables do not have
------------------------------------
`file_name`, `size_bytes` and `content_type` are new here because the design
lists each document by its name and shows "PDF · 2.4 MB". The existing tables
store only an s3_key, from which neither can be recovered — S3 HEAD would give
a size but costs a network round trip per row, and the original filename is
lost entirely once the key is a uuid.

`category` is the sidebar taxonomy (All / Identity / Financial / Property /
Other). It is the user's own filing, not a verification input.

Safety
------
A brand-new table cannot conflict with existing data. The partial index matches
the soft-delete convention so the common "my live documents" read stays cheap.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_create_user_documents"
down_revision: str | None = "0002_create_loan_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One statement per op.execute(): asyncpg runs these as prepared statements
    # and rejects multiple commands in one (see project alembic notes).
    op.execute(
        """
        CREATE TABLE user_documents (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES users(id),
            category            VARCHAR(20) NOT NULL
                                CHECK (category IN (
                                    'identity','financial','property','other'
                                )),
            file_name           TEXT NOT NULL,
            size_bytes          BIGINT NOT NULL CHECK (size_bytes > 0),
            content_type        VARCHAR(100) NOT NULL,
            s3_key              TEXT NOT NULL,
            verification_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (verification_status IN (
                                    'pending','verified','failed','under_review'
                                )),
            verified_by_user_id UUID REFERENCES users(id),
            verification_notes  TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ
        )
        """
    )
    # Serves both the list ("my live documents, newest first") and the status
    # counts the design's four stat cards need, from one index.
    op.execute(
        "CREATE INDEX idx_user_docs_owner ON user_documents(user_id, verification_status) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Drops the rows but NOT the S3 objects they point at. That is deliberate:
    # a downgrade must not issue storage deletes. The objects are unreachable
    # without a key (private bucket, no public URL); run an erasure sweep
    # separately if the bytes must actually go.
    op.execute("DROP TABLE user_documents")
