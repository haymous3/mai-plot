"""DB access for loan_documents (document-service's own table, SCRUM-131)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class LoanDocRow:
    id: UUID
    document_type: str
    s3_key: str
    verification_status: str
    created_at: datetime


class LoanDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_document(
        self, *, loan_id: UUID, document_type: str, s3_key: str, uploaded_by: UUID
    ) -> UUID:
        """Insert a loan_documents row (verification_status defaults to 'pending')
        and return its id."""
        document_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO loan_documents
                        (loan_id, document_type, s3_key, uploaded_by_user_id)
                    VALUES (:lid, :dtype, :s3, :by)
                    RETURNING id
                    """
                ),
                {"lid": loan_id, "dtype": document_type, "s3": s3_key, "by": uploaded_by},
            )
        ).scalar_one()
        assert isinstance(document_id, UUID)
        return document_id

    async def list_for_loan(self, loan_id: UUID) -> list[LoanDocRow]:
        """A loan's documents, newest first (excludes soft-deleted)."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, document_type, s3_key, verification_status, created_at
                    FROM loan_documents
                    WHERE loan_id = :lid AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """
                ),
                {"lid": loan_id},
            )
        ).all()
        return [
            LoanDocRow(
                id=r.id,
                document_type=r.document_type,
                s3_key=r.s3_key,
                verification_status=r.verification_status,
                created_at=r.created_at,
            )
            for r in rows
        ]
