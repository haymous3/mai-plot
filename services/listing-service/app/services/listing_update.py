"""Update-listing orchestration (PATCH /listings/{id}).

Only the owning seller or an admin may edit a listing, and a sold listing is
frozen. sale_type ↔ urgency ↔ expiry are kept consistent: converting to
distress requires a valid urgency tag (and re-derives expiry); converting to
normal clears the tag and sets a 90-day window (business rules §2/§3). The
cached detail (`listing:{id}`) is invalidated after a successful edit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.repositories.listing_repo import ListingRepository
from app.security import CurrentUser
from app.services.index_dispatch import IndexDispatcher
from app.services.listing_rules import resolve_urgency_and_expiry

logger = logging.getLogger(__name__)


class ListingUpdateError(RuntimeError):
    pass


class ListingNotFound(ListingUpdateError):
    """No live listing with that id."""


class NotListingOwner(ListingUpdateError):
    """Caller is neither the owning seller nor an admin."""


class CannotEditSoldListing(ListingUpdateError):
    """A sold listing is frozen."""


@dataclass(frozen=True)
class UpdateResult:
    listing_id: UUID
    status: str


class ListingUpdateService:
    def __init__(
        self,
        *,
        redis: Redis | None,
        listings: ListingRepository,
        dispatch: IndexDispatcher | None = None,
    ) -> None:
        self._redis = redis
        self._listings = listings
        self._dispatch = dispatch

    async def update(
        self, *, listing_id: UUID, caller: CurrentUser, changes: dict[str, object]
    ) -> UpdateResult:
        current = await self._listings.get_owner_status(listing_id)
        if current is None:
            raise ListingNotFound()
        if caller.role != "admin" and current.seller_id != caller.user_id:
            raise NotListingOwner()
        if current.status == "sold":
            raise CannotEditSoldListing()

        updates = self._build_updates(changes, current_sale_type=current.sale_type)
        if updates:
            await self._listings.apply_update(listing_id, updates)
        await self._invalidate(listing_id)
        # Re-sync search off the request path (edits change searchable fields).
        if self._dispatch is not None:
            await self._dispatch.enqueue(listing_id)
        return UpdateResult(listing_id=listing_id, status=current.status)

    def _build_updates(
        self, changes: dict[str, object], *, current_sale_type: str
    ) -> dict[str, object]:
        """Translate the partial request into column updates, keeping
        sale_type/urgency/expiry consistent."""
        updates: dict[str, object] = {}
        for field in (
            "title",
            "description",
            "property_type",
            "address_text",
            "lga",
            "state",
            "size_sqm",
            "asking_price_kobo",
        ):
            if field in changes:
                updates[field] = changes[field]

        if "location" in changes:
            loc = changes["location"]
            if isinstance(loc, dict):
                updates["location"] = f"SRID=4326;POINT({loc['lng']} {loc['lat']})"

        # sale_type / urgency / expiry interplay:
        if "sale_type" in changes:
            # A conversion re-derives urgency + expiry for the NEW sale type.
            new_sale_type = str(changes["sale_type"])
            urgency, expires = resolve_urgency_and_expiry(
                sale_type=new_sale_type,
                urgency_tag=_as_opt_str(changes.get("urgency_tag")),
            )
            updates["sale_type"] = new_sale_type
            updates["urgency_tag"] = urgency
            updates["expires_at"] = expires
        elif "urgency_tag" in changes and current_sale_type == "distress":
            # Changing the window on an existing distress sale re-derives expiry.
            urgency, expires = resolve_urgency_and_expiry(
                sale_type="distress", urgency_tag=_as_opt_str(changes["urgency_tag"])
            )
            updates["urgency_tag"] = urgency
            updates["expires_at"] = expires
        # An urgency tag on a normal sale (without a sale_type change) is not
        # applicable and is ignored.
        return updates

    async def _invalidate(self, listing_id: UUID) -> None:
        """Best-effort cache bust of the listing detail. A Redis failure here
        must not fail the (already-committed-on-success) update."""
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"listing:{listing_id}")
        except RedisError as exc:
            logger.warning(
                "redis.invalidate.failed", extra={"id": str(listing_id), "error": str(exc)}
            )


def _as_opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
