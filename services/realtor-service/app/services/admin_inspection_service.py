"""Admin placement of inspections (SCRUM-208).

Assignment was proximity-only and had no human in the loop: a buyer or seller
requested an inspection, the nearest approved realtor within 50km got it, and if
nobody was in range the request 503'd and vanished. An admin could not place one
— they are not a party to the transaction, so `POST /inspections` answered 403.

This service gives the admin two powers and no more:

  * **place** an inspection that is waiting for a realtor, choosing any APPROVED
    realtor, deliberately ignoring the radius; and
  * **create** an inspection for a transaction directly, with a chosen realtor or
    by trying proximity first.

Why the radius is bypassed rather than widened
----------------------------------------------
`find_nearest_approved` requires `base_location IS NOT NULL`, and onboarding
collects no location, so every realtor who signed up through the product is
invisible to proximity assignment no matter how large the radius. Widening it
would change nothing for them. Manual placement is currently the ONLY route from
a transaction to a real realtor's dashboard, so it must not inherit the filter
that excludes them.

What it deliberately cannot do
------------------------------
Move an inspection that is already offered, accepted or completed. Taking work
off a named realtor is a different decision with a different audit story, and it
is not what the dropped-request dead end needed.

Non-§11: no money, no state-machine transition, no schema change at call time.
Every placement writes an append-only audit row and notifies the realtor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.inspection_repo import (
    InspectionRepository,
    InspectionRow,
    UnassignedInspectionRow,
)
from app.repositories.realtor_repo import ApprovedRealtorRow, RealtorRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser
from app.services.inspection_notifier import InspectionNotifier

logger = logging.getLogger(__name__)


class AdminInspectionError(RuntimeError):
    pass


class InspectionNotFound(AdminInspectionError):
    """No inspection with that id."""


class InspectionNotUnassigned(AdminInspectionError):
    """The inspection already has a realtor — placement only fills an empty slot."""


class RealtorNotAssignable(AdminInspectionError):
    """No such realtor, or their application is not approved."""


class TransactionNotFound(AdminInspectionError):
    pass


class InspectionAlreadyActive(AdminInspectionError):
    """The transaction already has a live inspection."""


class InvalidProposedDate(AdminInspectionError):
    """The proposed inspection date is not in the future."""


class NoRealtorInRange(AdminInspectionError):
    """An auto-assign was asked for and proximity found nobody.

    Distinct from the buyer path, which records an unassigned row instead: here
    the admin explicitly asked "find someone", so "nobody" is the answer to their
    question, not a request that must not be lost.
    """


@dataclass(frozen=True)
class PlacementResult:
    inspection: InspectionRow
    realtor_id: UUID
    # False when the admin named the realtor, True when proximity chose them.
    auto_assigned: bool


class AdminInspectionService:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        realtors: RealtorRepository,
        transactions: TransactionRepository,
        audit: AuditLogRepository,
        notifier: InspectionNotifier,
        radius_meters: float,
        assignment_window_hours: int,
    ) -> None:
        self._inspections = inspections
        self._realtors = realtors
        self._transactions = transactions
        self._audit = audit
        self._notifier = notifier
        self._radius = radius_meters
        self._window_hours = assignment_window_hours

    async def list_unassigned(self, *, limit: int = 100) -> list[UnassignedInspectionRow]:
        """The queue of requests waiting for a realtor, oldest first."""
        return await self._inspections.list_unassigned(limit=limit)

    async def list_assignable_realtors(self, *, limit: int = 200) -> list[ApprovedRealtorRow]:
        """Approved realtors an admin may place work with — the picker source."""
        return await self._realtors.list_approved(limit=limit)

    async def place(
        self,
        *,
        inspection_id: UUID,
        realtor_id: UUID,
        admin: CurrentUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InspectionRow:
        """Assign an unassigned inspection to a named approved realtor."""
        await self._require_assignable(realtor_id)

        existing = await self._inspections.get(inspection_id)
        if existing is None:
            raise InspectionNotFound()
        if existing.status != "unassigned":
            raise InspectionNotUnassigned()

        placed = await self._inspections.place(
            inspection_id, realtor_id=realtor_id, window_hours=self._window_hours
        )
        if placed is None:
            # Lost a race with another admin (or the placement sweep). The guarded
            # UPDATE is the arbiter, so the loser writes no audit row and sends no
            # notification — the realtor who won is the only one told.
            raise InspectionNotUnassigned()

        await self._record(
            inspection_id=inspection_id,
            realtor_id=realtor_id,
            admin=admin,
            action="inspection.placed_by_admin",
            old_status="unassigned",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # The title is a nicety on an alert that must go out regardless, so a
        # missing transaction row costs the property name, not the notification.
        txn = await self._transactions.get(placed.transaction_id)
        await self._notify(
            realtor_id=realtor_id,
            inspection_id=inspection_id,
            property_title=txn.property_title if txn else None,
            proposed_date=placed.proposed_date,
        )
        return placed

    async def create(
        self,
        *,
        transaction_id: UUID,
        proposed_date: datetime,
        admin: CurrentUser,
        realtor_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PlacementResult:
        """Create an inspection for a transaction on the admin's authority.

        With `realtor_id` the named realtor is assigned. Without one, proximity is
        tried and `NoRealtorInRange` is raised if it finds nobody — an admin who
        asked us to choose deserves to be told we could not, rather than getting
        back a row that is still waiting.
        """
        if proposed_date <= datetime.now(UTC):
            raise InvalidProposedDate()

        txn = await self._transactions.get(transaction_id)
        if txn is None:
            raise TransactionNotFound()
        if await self._inspections.get_active_for_transaction(transaction_id) is not None:
            raise InspectionAlreadyActive()

        auto_assigned = realtor_id is None
        if realtor_id is None:
            found = await self._realtors.find_nearest_approved(
                listing_id=txn.listing_id, radius_m=self._radius
            )
            if found is None:
                raise NoRealtorInRange()
            realtor_id = found
        else:
            await self._require_assignable(realtor_id)

        inspection = await self._inspections.create(
            transaction_id=transaction_id,
            realtor_id=realtor_id,
            proposed_date=proposed_date,
            assignment_window_hours=self._window_hours,
        )
        await self._record(
            inspection_id=inspection.id,
            realtor_id=realtor_id,
            admin=admin,
            action="inspection.created_by_admin",
            old_status=None,
            ip_address=ip_address,
            user_agent=user_agent,
            extra={"transaction_id": str(transaction_id), "auto_assigned": auto_assigned},
        )
        await self._notify(
            realtor_id=realtor_id,
            inspection_id=inspection.id,
            property_title=txn.property_title,
            proposed_date=inspection.proposed_date,
        )
        return PlacementResult(
            inspection=inspection, realtor_id=realtor_id, auto_assigned=auto_assigned
        )

    async def _require_assignable(self, realtor_id: UUID) -> None:
        """A realtor must exist and be approved. An admin bypassing the RADIUS is
        the point of this service; bypassing the APPROVAL is not — that would put
        unvetted people in front of buyers at a property."""
        realtor = await self._realtors.get(realtor_id)
        if realtor is None or realtor.approval_status != "approved":
            raise RealtorNotAssignable()

    async def _record(
        self,
        *,
        inspection_id: UUID,
        realtor_id: UUID,
        admin: CurrentUser,
        action: str,
        old_status: str | None,
        ip_address: str | None,
        user_agent: str | None,
        extra: dict[str, object] | None = None,
    ) -> None:
        new_value: dict[str, object] = {"status": "pending", "realtor_id": str(realtor_id)}
        if extra:
            new_value.update(extra)
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action=action,
            entity_type="inspection",
            entity_id=inspection_id,
            old_value={"status": old_status} if old_status else None,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info(
            action,
            extra={"inspection_id": str(inspection_id), "realtor_id": str(realtor_id)},
        )

    async def _notify(
        self,
        *,
        realtor_id: UUID,
        inspection_id: UUID,
        property_title: str | None,
        proposed_date: datetime,
    ) -> None:
        """Best-effort: a broker outage must never undo a committed placement. The
        realtor still finds the assignment on their dashboard — the notification
        only makes it timely."""
        try:
            await self._notifier.assigned(
                realtor_id=realtor_id,
                inspection_id=inspection_id,
                property_title=property_title,
                proposed_date=proposed_date,
            )
        except Exception as exc:  # noqa: BLE001 — never fail a committed placement
            logger.warning(
                "inspection.place.notify_failed",
                extra={"inspection_id": str(inspection_id), "error": str(exc)},
            )
