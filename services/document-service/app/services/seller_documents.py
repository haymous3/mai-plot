"""Seller "Documents" list (SCRUM-98).

Read-only, non-§11: every document across the seller's listings, with the admin's
verification note surfaced (feedback on a rejection). The file itself is served
only via the watermarked view route, never here.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.document_repo import DocumentRepository
from app.schemas.document import SellerDocumentItem, SellerDocumentsResponse


class SellerDocumentsService:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents

    async def list_for_seller(self, seller_id: UUID) -> SellerDocumentsResponse:
        rows = await self._documents.list_for_seller(seller_id)
        return SellerDocumentsResponse(
            data=[
                SellerDocumentItem(
                    id=r.id,
                    listing_id=r.listing_id,
                    property_title=r.property_title,
                    document_type=r.document_type,
                    verification_status=r.verification_status,
                    verification_notes=r.verification_notes,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
