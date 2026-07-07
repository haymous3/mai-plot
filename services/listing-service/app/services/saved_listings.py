"""Save / unsave a listing + list a buyer's saved listings (SCRUM-95).

Powers the dashboard save-hearts and the Saved Properties card. Any authenticated
user may save a listing (buyers are the primary users; the design puts a heart on
every card). Non-§11: a favourites relationship, no money/state-machine/PII.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.listing_repo import FeedRow
from app.repositories.saved_repo import SavedListingRepository
from app.schemas.listing import FeedItem, FeedResponse, Pagination


def _to_item(r: FeedRow) -> FeedItem:
    return FeedItem(
        id=r.id,
        title=r.title,
        property_type=r.property_type,
        state=r.state,
        lga=r.lga,
        size_sqm=r.size_sqm,
        asking_price_kobo=r.asking_price_kobo,
        sale_type=r.sale_type,
        urgency_tag=r.urgency_tag,
        urgency_expires_at=r.expires_at,
        status=r.status,
        doc_verification_status=r.doc_verification_status,
        thumbnail_url=None,
        seller_authority_type=r.seller_authority_type,
        view_count=r.view_count,
        interest_count=r.interest_count,
        created_at=r.created_at,
    )


class SavedListingService:
    def __init__(self, *, saved: SavedListingRepository) -> None:
        self._saved = saved

    async def save(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        await self._saved.save(buyer_id=buyer_id, listing_id=listing_id)

    async def unsave(self, *, buyer_id: UUID, listing_id: UUID) -> None:
        await self._saved.unsave(buyer_id=buyer_id, listing_id=listing_id)

    async def list_saved(self, buyer_id: UUID) -> FeedResponse:
        rows = await self._saved.list_saved_feed(buyer_id)
        items = [_to_item(r) for r in rows]
        return FeedResponse(
            data=items,
            pagination=Pagination(
                page=1, page_size=len(items), total=len(items), total_pages=1 if items else 0
            ),
        )
