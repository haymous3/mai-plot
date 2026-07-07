"""List a listing's document verification metadata (SCRUM-95).

Powers the buyer property-detail "Document Verification" trust panel. Returns
only the document type + verification status — never the file, s3_key, or a URL
(the file is served solely via the watermarked pre-signed view route). Any
authenticated user may read this; it is public trust information on the listing.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.document_repo import DocumentRepository
from app.schemas.document import ListingDocumentMeta, ListingDocumentsResponse


class ListingDocumentListService:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents

    async def list_for_listing(self, listing_id: UUID) -> ListingDocumentsResponse:
        rows = await self._documents.list_for_listing(listing_id)
        return ListingDocumentsResponse(
            documents=[
                ListingDocumentMeta(
                    document_type=r.document_type, verification_status=r.verification_status
                )
                for r in rows
            ]
        )
