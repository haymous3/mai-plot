"""Index-sync dispatch seam (SCRUM-54).

The write path (create / edit / review / expiry) calls `enqueue(listing_id)`
to keep search in step with the DB — without doing the Elasticsearch I/O on
the request itself. Two transports share one Protocol:

  * CeleryIndexDispatcher — production. Hands the listing id to the
    `sync_listing_index` Celery task (retry + backoff live there). Enqueue is
    best-effort: a broker hiccup is logged, never raised, so it can't fail the
    write — the listing stays in Postgres with a NULL es_indexed_at for a later
    reconcile.
  * InlineIndexDispatcher — local/CI. Runs the same ListingIndexSync inline
    (best-effort) against the request's session + the in-memory fake index, so
    search is fresh without a broker or an ES cluster.

`build_index_dispatcher` picks the transport from settings
(`index_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.adapters.search_index import SearchIndex
from app.repositories.listing_repo import ListingRepository
from app.services.listing_index_sync import ListingIndexSync

logger = logging.getLogger(__name__)


class IndexDispatcher(Protocol):
    async def enqueue(self, listing_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CeleryIndexDispatcher:
    """Production transport — dispatch the sync to a Celery worker."""

    async def enqueue(self, listing_id: UUID) -> None:
        # Imported lazily so the request path (and tests) never import Celery
        # task wiring unless this transport is actually used.
        try:
            from app.tasks.listing_index import sync_listing_index

            sync_listing_index.delay(str(listing_id))
        except Exception as exc:  # broker down etc. — never fail the write
            logger.warning(
                "listing.index.enqueue_failed",
                extra={"id": str(listing_id), "error": str(exc)},
            )


class InlineIndexDispatcher:
    """Local/CI transport — run the sync inline (best-effort), no broker."""

    def __init__(self, *, sync: ListingIndexSync) -> None:
        self._sync = sync

    async def enqueue(self, listing_id: UUID) -> None:
        await self._sync.sync_safe(listing_id)


def build_index_dispatcher(
    *, via_celery: bool, index: SearchIndex, listings: ListingRepository
) -> IndexDispatcher:
    if via_celery:
        return CeleryIndexDispatcher()
    return InlineIndexDispatcher(sync=ListingIndexSync(index=index, listings=listings))
