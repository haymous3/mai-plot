"""Listing detail query (GET /listings/{id}).

The viewer-independent listing body is Redis-cached under `listing:{id}` for
`listing_cache_ttl_seconds`; loan eligibility (which depends on whether the
caller is a buyer) is computed per-request AFTER the cache read, so the
cached entry is identical for every viewer. A 404 is never cached — the
loader raises and the exception short-circuits the cache write.
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

from app.adapters.redis_cache import get_with_fallback
from app.repositories.listing_repo import ListingRepository
from app.repositories.seller_repo import SellerRepository
from app.schemas.listing import (
    GeoPoint,
    ListingDetailResponse,
    MediaItem,
    SellerBlock,
)
from app.security import CurrentUser
from app.services.view_count_dispatch import ViewCountDispatcher

# Maximum loan = 50% of the asking price (business rule §5).
_LOAN_FRACTION_DENOMINATOR = 2


class ListingNotFound(Exception):
    """No live listing with that id."""


class ListingDetailService:
    def __init__(
        self,
        *,
        redis: Redis | None,
        listings: ListingRepository,
        sellers: SellerRepository,
        ttl_seconds: int,
        view_counter: ViewCountDispatcher | None = None,
    ) -> None:
        self._redis = redis
        self._listings = listings
        self._sellers = sellers
        self._ttl = ttl_seconds
        self._view_counter = view_counter

    async def get_detail(
        self, *, listing_id: UUID, viewer: CurrentUser | None
    ) -> ListingDetailResponse | None:
        try:
            base = await get_with_fallback(
                self._redis,
                f"listing:{listing_id}",
                lambda: self._load_base(listing_id),
                ttl_seconds=self._ttl,
                serialiser=lambda r: r.model_dump_json(),
                deserialiser=ListingDetailResponse.model_validate_json,
            )
        except ListingNotFound:
            return None

        # Every successful view counts (cache hit or miss; anonymous too). The
        # bump is dispatched off the request path (Celery in prod, inline in
        # dev/CI) and is best-effort — it never affects this read.
        if self._view_counter is not None:
            await self._view_counter.enqueue(listing_id)

        # Loan eligibility is viewer-specific, so it is applied after the
        # (viewer-independent) cache read. Only an authenticated buyer sees it.
        loan_kobo = (
            base.asking_price_kobo // _LOAN_FRACTION_DENOMINATOR
            if viewer is not None and viewer.role == "buyer"
            else None
        )
        return base.model_copy(update={"loan_eligibility_kobo": loan_kobo})

    async def _load_base(self, listing_id: UUID) -> ListingDetailResponse:
        row = await self._listings.get_detail(listing_id)
        if row is None:
            raise ListingNotFound()

        seller = await self._sellers.get_seller_public(row.seller_id)
        media = await self._listings.list_media(listing_id)

        return ListingDetailResponse(
            id=row.id,
            seller=SellerBlock(
                id=row.seller_id,
                authority_type=seller.authority_type if seller else None,
                poa_owner_name=seller.poa_owner_name if seller else None,
            ),
            title=row.title,
            description=row.description,
            address_text=row.address_text,
            location=GeoPoint(lat=row.lat, lng=row.lng),
            size_sqm=row.size_sqm,
            asking_price_kobo=row.asking_price_kobo,
            sale_type=row.sale_type,
            urgency_tag=row.urgency_tag,
            urgency_expires_at=row.expires_at,
            status=row.status,
            media=[
                MediaItem(type=m.media_type, url=m.cdn_url, sort_order=m.sort_order) for m in media
            ],
            # Filled per-viewer above; the cached base is always None.
            loan_eligibility_kobo=None,
            view_count=row.view_count,
            interest_count=row.interest_count,
        )
