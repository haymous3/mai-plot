"""Admin document review queue (GET /admin/documents/queue).

Serves one queue over BOTH document tables, selected by `source`:

  * `listing`  — `listing_documents`, a seller's legal paperwork for a property
  * `personal` — `user_documents`, a person's own identity/financial documents
                 uploaded from My Documents (SCRUM-188)

They are one endpoint rather than two because migration 0003 deliberately gave
`user_documents` the SAME verification vocabulary as the other document tables
so the review workflow could treat them alike. Splitting them here would fork
the review logic, the audit trail and the UI for no gain.
"""

from __future__ import annotations

from app.repositories.document_repo import DocumentRepository
from app.repositories.user_document_repo import UserDocumentRepository
from app.schemas.document import DocQueueItem, DocQueueResponse, DocSource, Pagination


class AdminQueueService:
    def __init__(
        self, *, documents: DocumentRepository, user_documents: UserDocumentRepository
    ) -> None:
        self._documents = documents
        self._user_documents = user_documents

    async def list_queue(
        self, *, source: DocSource, status: str, page: int, page_size: int
    ) -> DocQueueResponse:
        items: list[DocQueueItem]
        if source == "personal":
            personal_rows, total = await self._user_documents.list_queue(
                status=status, page=page, page_size=page_size
            )
            items = [
                DocQueueItem(
                    id=r.id,
                    source="personal",
                    verification_status=r.verification_status,
                    created_at=r.created_at,
                    user_id=r.user_id,
                    owner_name=r.owner_name,
                    category=r.category,
                    file_name=r.file_name,
                    size_bytes=r.size_bytes,
                )
                for r in personal_rows
            ]
        else:
            listing_rows, total = await self._documents.list_queue(
                status=status, page=page, page_size=page_size
            )
            items = [
                DocQueueItem(
                    id=r.id,
                    source="listing",
                    verification_status=r.verification_status,
                    created_at=r.created_at,
                    listing_id=r.listing_id,
                    document_type=r.document_type,
                )
                for r in listing_rows
            ]

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return DocQueueResponse(
            data=items,
            pagination=Pagination(
                page=page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )
