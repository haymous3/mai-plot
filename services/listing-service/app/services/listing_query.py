"""Listing feed query (GET /listings).

Postgres-backed (the feed is a filtered list, not full-text search — that is
GET /listings/search on Elasticsearch). Results are Redis-cached per filter
set for `feed_cache_ttl_seconds`; a Redis failure falls back to Postgres via
get_with_fallback and never crashes the request.
"""

from __future__ import annotations

import hashlib
import json

from redis.asyncio import Redis

from app.adapters.redis_cache import get_with_fallback
from app.repositories.listing_repo import FeedFilters, ListingRepository
from app.schemas.listing import FeedItem, FeedResponse, Pagination


def _cache_key(filters: FeedFilters) -> str:
    """Stable cache key from the full filter set. CLAUDE.md lists
    `feed:{state}:{page}`, but the feed takes many filters, so we hash the
    whole normalised set under the `feed:` prefix to avoid cross-filter
    collisions."""
    payload = json.dumps(filters.__dict__, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"feed:{digest}"


class ListingQueryService:
    def __init__(
        self, *, redis: Redis | None, listings: ListingRepository, ttl_seconds: int
    ) -> None:
        self._redis = redis
        self._listings = listings
        self._ttl = ttl_seconds

    async def get_feed(self, filters: FeedFilters) -> FeedResponse:
        return await get_with_fallback(
            self._redis,
            _cache_key(filters),
            lambda: self._load(filters),
            ttl_seconds=self._ttl,
            serialiser=lambda r: r.model_dump_json(),
            deserialiser=FeedResponse.model_validate_json,
        )

    async def _load(self, filters: FeedFilters) -> FeedResponse:
        rows, total = await self._listings.list_feed(filters)
        items = [
            FeedItem(
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
                # Populated once media upload (POST /listings/{id}/media) lands.
                thumbnail_url=None,
                seller_authority_type=r.seller_authority_type,
                view_count=r.view_count,
                interest_count=r.interest_count,
                created_at=r.created_at,
            )
            for r in rows
        ]
        page_size = filters.page_size
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return FeedResponse(
            data=items,
            pagination=Pagination(
                page=filters.page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
