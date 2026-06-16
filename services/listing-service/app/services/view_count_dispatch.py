"""view_count dispatch seam (SCRUM-114).

A listing detail view bumps view_count without doing the write on the GET. Two
transports share one Protocol:

  * CeleryViewCountDispatcher — production. Hands the listing id to the
    `increment_view_count` Celery task. Enqueue is best-effort: a broker hiccup
    is logged, never raised, so view-counting can't slow or fail a read.
  * InlineViewCountDispatcher — local/CI. Increments via the request's
    repository inline (best-effort), so the behaviour is exercised without a
    broker. (This is the only path that writes in-request; production always
    goes through Celery, per the AC.)

`build_view_count_dispatcher` picks the transport from settings
(`view_count_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.repositories.listing_repo import ListingRepository

logger = logging.getLogger(__name__)


class ViewCountDispatcher(Protocol):
    async def enqueue(self, listing_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CeleryViewCountDispatcher:
    """Production transport — dispatch the increment to a Celery worker."""

    async def enqueue(self, listing_id: UUID) -> None:
        try:
            from app.tasks.view_count import increment_view_count

            increment_view_count.delay(str(listing_id))
        except Exception as exc:  # broker down etc. — never affect the read
            logger.warning(
                "listing.view_count.enqueue_failed",
                extra={"id": str(listing_id), "error": str(exc)},
            )


class InlineViewCountDispatcher:
    """Local/CI transport — increment inline (best-effort), no broker."""

    def __init__(self, *, listings: ListingRepository) -> None:
        self._listings = listings

    async def enqueue(self, listing_id: UUID) -> None:
        try:
            await self._listings.increment_view_count(listing_id)
        except Exception as exc:  # best-effort: never break the read
            logger.warning(
                "listing.view_count.inline_failed",
                extra={"id": str(listing_id), "error": str(exc)},
            )


def build_view_count_dispatcher(
    *, via_celery: bool, listings: ListingRepository
) -> ViewCountDispatcher:
    if via_celery:
        return CeleryViewCountDispatcher()
    return InlineViewCountDispatcher(listings=listings)
