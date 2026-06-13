"""Admin document review queue (GET /admin/documents/queue)."""

from __future__ import annotations

from app.repositories.document_repo import DocumentRepository
from app.schemas.document import DocQueueItem, DocQueueResponse, Pagination


class AdminQueueService:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents

    async def list_queue(self, *, status: str, page: int, page_size: int) -> DocQueueResponse:
        rows, total = await self._documents.list_queue(
            status=status, page=page, page_size=page_size
        )
        items = [
            DocQueueItem(
                id=r.id,
                listing_id=r.listing_id,
                document_type=r.document_type,
                verification_status=r.verification_status,
                created_at=r.created_at,
            )
            for r in rows
        ]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return DocQueueResponse(
            data=items,
            pagination=Pagination(
                page=page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )
