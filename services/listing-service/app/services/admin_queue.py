"""Admin review queue (GET /admin/listings/queue)."""

from __future__ import annotations

from app.repositories.listing_repo import ListingRepository
from app.schemas.listing import AdminQueueItem, AdminQueueResponse, Pagination


class AdminQueueService:
    def __init__(self, *, listings: ListingRepository) -> None:
        self._listings = listings

    async def list_queue(
        self, *, status: str, authority_type: str | None, page: int, page_size: int
    ) -> AdminQueueResponse:
        rows, total = await self._listings.list_review_queue(
            status=status, authority_type=authority_type, page=page, page_size=page_size
        )
        items = [
            AdminQueueItem(
                id=r.id,
                seller_id=r.seller_id,
                title=r.title,
                state=r.state,
                lga=r.lga,
                asking_price_kobo=r.asking_price_kobo,
                sale_type=r.sale_type,
                status=r.status,
                seller_authority_type=r.seller_authority_type,
                created_at=r.created_at,
            )
            for r in rows
        ]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return AdminQueueResponse(
            data=items,
            pagination=Pagination(
                page=page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )
