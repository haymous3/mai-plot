"""Elasticsearch sync for a single listing (SCRUM-54).

One operation: reconcile a listing's presence in the search index with its
current DB state.

  * A listing in an *indexable* status -> upsert its document.
  * A deleted listing (no live row) or one in a terminal/hidden status
    (expired, rejected, cancelled, sold) -> remove it from the index.

After a successful sync the listing's `es_indexed_at` is stamped, so an
un-synced listing (NULL es_indexed_at) is identifiable for a future reconcile
sweep.

`sync()` RAISES on failure — that is what lets the Celery task retry with
backoff. `sync_safe()` is the swallow-and-log variant for inline/batch callers
(local/CI dispatch, the expiry job) where one index hiccup must not abort the
surrounding work.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.search_index import SearchIndex
from app.repositories.listing_repo import ListingRepository

logger = logging.getLogger(__name__)

# Statuses whose documents belong in the search index. Everything else
# (expired, rejected, cancelled, sold) is removed so the index never serves a
# stale document. 'pending_review' is indexed but excluded at query time, so an
# approval is a cheap status update rather than a fresh insert.
INDEXABLE_STATUSES = frozenset({"active", "pending_review", "under_offer"})


class ListingIndexSync:
    def __init__(self, *, index: SearchIndex, listings: ListingRepository) -> None:
        self._index = index
        self._listings = listings

    async def sync(self, listing_id: UUID) -> str:
        """Reconcile the listing's index document. Returns 'upserted' or
        'deleted'. Raises on any index/DB failure (the Celery task retries)."""
        doc = await self._listings.get_search_doc(listing_id)
        if doc is None or doc.status not in INDEXABLE_STATUSES:
            # Deleted (no live row) or terminal/hidden -> drop from the index.
            await self._index.delete(listing_id)
            await self._listings.mark_es_indexed(listing_id)
            return "deleted"
        await self._index.upsert(doc)
        await self._listings.mark_es_indexed(listing_id)
        return "upserted"

    async def sync_safe(self, listing_id: UUID) -> None:
        """Best-effort sync: swallow + log any failure. For inline dispatch and
        batch jobs where indexing must never break the surrounding write."""
        try:
            await self.sync(listing_id)
        except Exception as exc:  # best-effort: never break the caller
            logger.warning(
                "listing.index.sync_failed",
                extra={"id": str(listing_id), "error": str(exc)},
            )
