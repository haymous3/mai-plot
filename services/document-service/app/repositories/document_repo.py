"""DB writes for listing_documents (document-service's own table)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_document(self, *, listing_id: UUID, document_type: str, s3_key: str) -> UUID:
        """Insert a listing_documents row (verification_status defaults to
        'pending') and return its id."""
        document_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO listing_documents (listing_id, document_type, s3_key)
                    VALUES (:lid, :dtype, :s3)
                    RETURNING id
                    """
                ),
                {"lid": listing_id, "dtype": document_type, "s3": s3_key},
            )
        ).scalar_one()
        assert isinstance(document_id, UUID)
        return document_id
