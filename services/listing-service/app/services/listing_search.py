"""Listing search query (GET /listings/search).

Elasticsearch-backed (CLAUDE.md non-negotiable). Translates the request into
a SearchParams, runs it through the index adapter, and shapes the hits into
the feed item format plus a search_score.
"""

from __future__ import annotations

from app.adapters.search_index import SearchIndex, SearchParams
from app.schemas.listing import Pagination, SearchItem, SearchResponse


class ListingSearchService:
    def __init__(self, *, index: SearchIndex) -> None:
        self._index = index

    async def search(self, params: SearchParams) -> SearchResponse:
        hits, total = await self._index.search(params)
        items = [
            SearchItem(
                id=h.doc.id,
                title=h.doc.title,
                property_type=h.doc.property_type,
                state=h.doc.state,
                lga=h.doc.lga,
                size_sqm=h.doc.size_sqm,
                asking_price_kobo=h.doc.asking_price_kobo,
                sale_type=h.doc.sale_type,
                urgency_tag=h.doc.urgency_tag,
                urgency_expires_at=h.doc.expires_at,
                status=h.doc.status,
                doc_verification_status=h.doc.doc_verification_status,
                thumbnail_url=None,
                seller_authority_type=h.doc.seller_authority_type,
                view_count=h.doc.view_count,
                interest_count=h.doc.interest_count,
                created_at=h.doc.created_at,
                search_score=h.score,
            )
            for h in hits
        ]
        page_size = params.page_size
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return SearchResponse(
            data=items,
            pagination=Pagination(
                page=params.page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )
