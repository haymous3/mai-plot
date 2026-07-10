"""Inspection auto-assignment (SCRUM-72).

A party to a transaction requests an inspection; the nearest approved realtor
within the radius is assigned with a 2-hour acceptance window, and notified. The
assigned realtor accepts within the window. If nobody is in range, an admin
alert is logged (the fallback) and the request fails.

Reassignment of a lapsed (unaccepted) window is a follow-up Celery sweep — the
algorithm here (`find_nearest_approved` with an exclude list) is built to support
it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.inspection_repo import (
    AssignedRealtorRow,
    InspectionRepository,
    InspectionRow,
    RealtorInspectionRow,
)
from app.repositories.realtor_repo import RealtorRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser
from app.services.inspection_notifier import InspectionNotifier

logger = logging.getLogger(__name__)


class InspectionError(RuntimeError):
    pass


class TransactionNotFound(InspectionError):
    pass


class NotTransactionParty(InspectionError):
    """Caller is neither the buyer nor the seller on the transaction."""


class InspectionAlreadyActive(InspectionError):
    """The transaction already has a live inspection."""


class NoRealtorAvailable(InspectionError):
    """No approved realtor with a base location is within the radius."""


class InspectionNotFound(InspectionError):
    pass


class NotAssignedRealtor(InspectionError):
    """Caller is not the realtor this inspection was assigned to."""


class InspectionNotPending(InspectionError):
    pass


class AssignmentExpired(InspectionError):
    """The 2-hour acceptance window has elapsed."""


class InspectionService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        realtors: RealtorRepository,
        inspections: InspectionRepository,
        notifier: InspectionNotifier,
        radius_meters: float,
        assignment_window_hours: int,
    ) -> None:
        self._transactions = transactions
        self._realtors = realtors
        self._inspections = inspections
        self._notifier = notifier
        self._radius = radius_meters
        self._window_hours = assignment_window_hours

    async def request(
        self, *, caller: CurrentUser, transaction_id: UUID, proposed_date: datetime
    ) -> InspectionRow:
        txn = await self._transactions.get(transaction_id)
        if txn is None:
            raise TransactionNotFound()
        if caller.user_id not in (txn.buyer_id, txn.seller_id):
            raise NotTransactionParty()
        if await self._inspections.get_active_for_transaction(transaction_id) is not None:
            raise InspectionAlreadyActive()

        realtor_id = await self._realtors.find_nearest_approved(
            listing_id=txn.listing_id, radius_m=self._radius
        )
        if realtor_id is None:
            # Fallback (AC): no realtor in range — surface a high-visibility alert
            # for ops/admin (there is no single admin user to push to).
            logger.warning(
                "inspection.no_realtor_available",
                extra={"transaction_id": str(transaction_id), "listing_id": str(txn.listing_id)},
            )
            raise NoRealtorAvailable()

        inspection = await self._inspections.create(
            transaction_id=transaction_id,
            realtor_id=realtor_id,
            proposed_date=proposed_date,
            assignment_window_hours=self._window_hours,
        )
        await self._notify_assigned(realtor_id=realtor_id, inspection_id=inspection.id)
        logger.info(
            "inspection.assigned",
            extra={"inspection_id": str(inspection.id), "transaction_id": str(transaction_id)},
        )
        return inspection

    async def assigned_realtor_for_transaction(
        self, *, caller: CurrentUser, transaction_id: UUID
    ) -> AssignedRealtorRow | None:
        """Who is assigned to inspect this transaction's property (SCRUM-139).
        Only a party to the transaction may see it; returns None when no
        inspection has been requested yet. Identity only — no contact details."""
        txn = await self._transactions.get(transaction_id)
        if txn is None:
            raise TransactionNotFound()
        if caller.user_id not in (txn.buyer_id, txn.seller_id):
            raise NotTransactionParty()
        return await self._inspections.latest_assignment_for_transaction(transaction_id)

    async def list_for_realtor(
        self, *, caller: CurrentUser, limit: int = 100
    ) -> list[RealtorInspectionRow]:
        """Every inspection assigned to the calling realtor, newest first — the
        realtor portal's dashboard + assigned-inspections feed (SCRUM-140). A
        non-realtor caller simply has no assignments, so this returns []."""
        return await self._inspections.list_for_realtor(caller.user_id, limit=limit)

    async def accept(self, *, caller: CurrentUser, inspection_id: UUID) -> InspectionRow:
        inspection = await self._inspections.get(inspection_id)
        if inspection is None:
            raise InspectionNotFound()
        if inspection.realtor_id != caller.user_id:
            raise NotAssignedRealtor()
        if inspection.status != "pending":
            raise InspectionNotPending()
        if inspection.assignment_expires_at <= datetime.now(UTC):
            raise AssignmentExpired()

        await self._inspections.mark_accepted(inspection_id)
        accepted = await self._inspections.get(inspection_id)
        assert accepted is not None
        return accepted

    async def _notify_assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None:
        """Best-effort + defensive — a notification failure never fails the
        assignment (the inspection row is the source of truth)."""
        try:
            await self._notifier.assigned(realtor_id=realtor_id, inspection_id=inspection_id)
        except Exception as exc:  # noqa: BLE001 — never fail the assignment
            logger.warning(
                "inspection.notify_failed",
                extra={"inspection_id": str(inspection_id), "error": str(exc)},
            )
