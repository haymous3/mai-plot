"""Index-on-write helper for listing search.

After a listing is created or edited, its document is upserted into the
search index. This is BEST-EFFORT: an index failure must never fail the
DB write (the source of truth is Postgres; a missed index update is healed
by the next edit or a reindex). CLAUDE.md prefers async-via-Celery, but
Celery is not wired into listing-service yet — index-on-write keeps search
fresh without it, and the swallow-on-error keeps writes resilient.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.search_index import SearchIndex
from app.repositories.listing_repo import ListingRepository

logger = logging.getLogger(__name__)


class ListingIndexer:
    def __init__(self, *, index: SearchIndex, listings: ListingRepository) -> None:
        self._index = index
        self._listings = listings

    async def reindex_safe(self, listing_id: UUID) -> None:
        """Upsert the listing's search document; swallow + log any failure."""
        try:
            doc = await self._listings.get_search_doc(listing_id)
            if doc is not None:
                await self._index.upsert(doc)
        except Exception as exc:  # best-effort: never break the write path
            logger.warning("listing.index.failed", extra={"id": str(listing_id), "error": str(exc)})
