"""DB access for listing_documents (document-service's own table)."""

from __future__ import annotations

import json
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
class ViewDoc:
    s3_key: str
    verification_status: str
    listing_id: UUID
    seller_id: UUID


@dataclass(frozen=True)
class QueueRow:
    id: UUID
    listing_id: UUID
    document_type: str
    verification_status: str
    created_at: datetime


@dataclass(frozen=True)
class DocMetaRow:
    """Public verification metadata for a listing's documents — no s3_key/url."""

    document_type: str
    verification_status: str


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

    async def list_for_listing(self, listing_id: UUID) -> list[DocMetaRow]:
        """A listing's documents' verification metadata (type + status only),
        for the buyer detail page's trust panel. Never returns s3_key/url — the
        file itself is served only via the watermarked pre-signed view route."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT document_type, verification_status
                    FROM listing_documents
                    WHERE listing_id = :lid
                    ORDER BY created_at
                    """
                ),
                {"lid": listing_id},
            )
        ).all()
        return [
            DocMetaRow(document_type=r.document_type, verification_status=r.verification_status)
            for r in rows
        ]

    async def get_ocr_source(self, document_id: UUID) -> str | None:
        """The S3 key OCR should read, or None if the document is gone."""
        row = (
            await self._session.execute(
                text("SELECT s3_key FROM listing_documents WHERE id = :id"),
                {"id": document_id},
            )
        ).first()
        return row.s3_key if row is not None else None

    async def store_ocr_result(self, document_id: UUID, data: dict[str, str]) -> None:
        """Store extracted OCR fields as JSONB. Verification status is left
        untouched — a successful read does not auto-verify the document."""
        await self._session.execute(
            text(
                "UPDATE listing_documents "
                "SET ocr_extracted_data = CAST(:data AS jsonb), updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"data": json.dumps(data), "id": document_id},
        )

    async def flag_for_manual_review(
        self, document_id: UUID, *, note: str, data: dict[str, str] | None = None
    ) -> None:
        """OCR could not produce usable fields: store whatever was read and move
        the document to 'under_review' so the legal team checks it by hand."""
        await self._session.execute(
            text(
                "UPDATE listing_documents "
                "SET verification_status = 'under_review', "
                "    ocr_extracted_data = CAST(:data AS jsonb), "
                "    verification_notes = :note, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"data": json.dumps(data or {}), "note": note, "id": document_id},
        )

    async def get_view(self, document_id: UUID) -> ViewDoc | None:
        """The S3 key + verification status + listing/seller of a document, for
        serving (the listing/seller drive the view authorization check)."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT ld.s3_key, ld.verification_status, ld.listing_id, pl.seller_id
                    FROM listing_documents ld
                    JOIN property_listings pl ON pl.id = ld.listing_id
                    WHERE ld.id = :id AND pl.deleted_at IS NULL
                    """
                ),
                {"id": document_id},
            )
        ).first()
        if row is None:
            return None
        return ViewDoc(
            s3_key=row.s3_key,
            verification_status=row.verification_status,
            listing_id=row.listing_id,
            seller_id=row.seller_id,
        )

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
