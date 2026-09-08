"""Admin power over a live listing (SCRUM-215).

Admin control of a listing stopped at the front door: approve or reject it once,
while it was `pending_review`, and after that nothing. A listing that turned out
to be fraudulent, duplicated, or simply wrong stayed on the marketplace with no
way for an admin to take it down.

Three actions, and only three:

  * **pause / unpause** (`active` <-> `paused`) — the seller's own visibility
    toggle, exercised by an admin. Reversible, and the mildest thing that
    actually removes a listing from the feed.
  * **take down** (`active`/`paused` -> `rejected`, reason REQUIRED) — reuses the
    rejection status and `rejection_reason` the seller is already shown, so a
    taken-down listing reads to its owner exactly like a rejected one, with the
    admin's words attached. No new status, no new seller-facing concept.
  * **expire** (`active` -> `expired`) — the expiry sweep's own transition,
    applied early. For a listing that is simply stale rather than wrong.

What it deliberately cannot do
------------------------------
**Touch a listing that is `under_offer`.** That status is the §8 rule-4 lock: a
buyer's offer has been accepted, the listing is held for 72 hours, and there may
be escrow behind it. Pulling it out from under a live transaction is not a
listing decision, it is a deal decision — so it is refused with a code that says
to resolve the transaction first. `sold` is terminal for the same reason.

It also cannot EDIT a listing. Price, description and photos are the seller's
content; an admin rewriting them makes "who wrote this" unanswerable.

Non-§11: no money, no transaction-state transition, no schema change. Every
action writes an append-only audit row and re-indexes.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.security import CurrentUser
from app.services.index_dispatch import IndexDispatcher

logger = logging.getLogger(__name__)

# action -> (target status, statuses it may be applied from, audit verb)
_ACTIONS: Final[dict[str, tuple[str, tuple[str, ...], str]]] = {
    "pause": ("paused", ("active",), "listing.paused_by_admin"),
    "unpause": ("active", ("paused",), "listing.unpaused_by_admin"),
    "take_down": ("rejected", ("active", "paused"), "listing.taken_down_by_admin"),
    "expire": ("expired", ("active",), "listing.expired_by_admin"),
}

# The §8 rule-4 lock. Refused with its own code because the remedy is different:
# an admin has to resolve the transaction, not retry the listing action.
_LOCKED_STATUS: Final = "under_offer"


class AdminListingActionError(RuntimeError):
    pass


class ListingNotFound(AdminListingActionError):
    pass


class ReasonRequired(AdminListingActionError):
    """A take-down must say why — the seller is shown this text."""


class ListingUnderOffer(AdminListingActionError):
    """A buyer's accepted offer is holding this listing (§8 rule 4)."""


class ListingStatusConflict(AdminListingActionError):
    """The listing is not in a status this action can be applied from."""

    def __init__(self, current: str, action: str) -> None:
        super().__init__(f"cannot {action} a listing in status {current}")
        self.current = current
        self.action = action


class AdminListingActionsService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        audit: AuditLogRepository,
        dispatch: IndexDispatcher | None = None,
    ) -> None:
        self._listings = listings
        self._audit = audit
        self._dispatch = dispatch

    async def apply(
        self,
        *,
        listing_id: UUID,
        action: str,
        admin: CurrentUser,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """Apply an action and return the listing's new status."""
        new_status, allowed_from, audit_action = _ACTIONS[action]

        cleaned = (reason or "").strip()
        if action == "take_down" and not cleaned:
            raise ReasonRequired()

        current = await self._listings.get_owner_status(listing_id)
        if current is None:
            raise ListingNotFound()
        if current.status == _LOCKED_STATUS:
            raise ListingUnderOffer()
        if current.status not in allowed_from:
            raise ListingStatusConflict(current.status, action)

        applied = await self._listings.set_status_guarded(
            listing_id,
            new_status=new_status,
            expected=allowed_from,
            rejection_reason=cleaned if action == "take_down" else None,
        )
        if not applied:
            # Lost a race with another admin, the expiry sweep, or the seller's
            # own pause. The guarded UPDATE decided; report the state we read.
            raise ListingStatusConflict(current.status, action)

        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action=audit_action,
            entity_type="listing",
            entity_id=listing_id,
            old_value={"status": current.status},
            new_value={"status": new_status, "reason": cleaned or None},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Every one of these changes whether the listing belongs in the index:
        # paused, rejected and expired are all absent from INDEXABLE_STATUSES,
        # and unpause puts it back. Skipping this is exactly the bug that left
        # paused listings findable in search.
        if self._dispatch is not None:
            await self._dispatch.enqueue(listing_id)

        logger.info(
            audit_action,
            extra={"listing_id": str(listing_id), "from": current.status, "to": new_status},
        )
        return new_status
