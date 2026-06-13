"""DB access for listing_documents (document-service's own table)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class DocStatus:
    listing_id: UUID
    verification_status: str


@dataclass(frozen=True)
class QueueRow:
    id: UUID
    listing_id: UUID
    document_type: str
    verification_status: str
    created_at: datetime


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

    async def get_status(self, document_id: UUID) -> DocStatus | None:
        """The listing + current verification status of a document, or None."""
        row = (
            await self._session.execute(
                text(
                    "SELECT listing_id, verification_status FROM listing_documents WHERE id = :id"
                ),
                {"id": document_id},
            )
        ).first()
        if row is None:
            return None
        return DocStatus(listing_id=row.listing_id, verification_status=row.verification_status)

    async def set_verification(
        self,
        document_id: UUID,
        *,
        status: str,
        verified_by_user_id: UUID,
        notes: str | None,
    ) -> None:
        """Apply an admin verification decision to a listing_documents row."""
        await self._session.execute(
            text(
                "UPDATE listing_documents "
                "SET verification_status = :s, verified_by_user_id = :by, "
                "    verification_notes = :notes, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"s": status, "by": verified_by_user_id, "notes": notes, "id": document_id},
        )

    async def list_queue(
        self, *, status: str, page: int, page_size: int
    ) -> tuple[list[QueueRow], int]:
        """Documents in a given verification status, oldest-first (FIFO)."""
        total = (
            await self._session.execute(
                text("SELECT COUNT(*) FROM listing_documents WHERE verification_status = :s"),
                {"s": status},
            )
        ).scalar_one()
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, listing_id, document_type, verification_status, created_at
                    FROM listing_documents
                    WHERE verification_status = :s
                    ORDER BY created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"s": status, "limit": page_size, "offset": (page - 1) * page_size},
            )
        ).all()
        items = [
            QueueRow(
                id=r.id,
                listing_id=r.listing_id,
                document_type=r.document_type,
                verification_status=r.verification_status,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, int(total)
