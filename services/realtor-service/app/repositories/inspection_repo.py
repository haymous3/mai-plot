"""Access to the inspections table (owned by realtor-service, SCRUM-72).

An inspection is created already assigned to the nearest approved realtor, with a
2-hour acceptance window (assignment_expires_at). The realtor accepts within the
window; a lapsed window is reassigned by a follow-up sweep.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# An inspection in one of these statuses is "live" — a transaction can't have a
# second one requested while one is outstanding.
_ACTIVE_STATUSES = ("pending", "accepted", "rescheduled")


@dataclass(frozen=True)
class InspectionRow:
    id: UUID
    transaction_id: UUID
    realtor_id: UUID
    proposed_date: datetime
    confirmed_date: datetime | None
    status: str
    assignment_expires_at: datetime
    created_at: datetime


_COLUMNS = (
    "id, transaction_id, realtor_id, proposed_date, confirmed_date, status, "
    "assignment_expires_at, created_at"
)


class InspectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, inspection_id: UUID) -> InspectionRow | None:
        row = (
            await self._session.execute(
                text(f"SELECT {_COLUMNS} FROM inspections WHERE id = :id"),
                {"id": inspection_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def get_active_for_transaction(self, transaction_id: UUID) -> InspectionRow | None:
        row = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM inspections "
                    "WHERE transaction_id = :tx AND status = ANY(:statuses) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"tx": transaction_id, "statuses": list(_ACTIVE_STATUSES)},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def create(
        self,
        *,
        transaction_id: UUID,
        realtor_id: UUID,
        proposed_date: datetime,
        assignment_window_hours: int,
    ) -> InspectionRow:
        """Create a pending inspection assigned to `realtor_id`, with the
        acceptance window starting now."""
        row = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO inspections
                        (transaction_id, realtor_id, proposed_date, status,
                         assignment_expires_at)
                    VALUES
                        (:tx, :realtor, :proposed, 'pending',
                         NOW() + make_interval(hours => :hours))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "tx": transaction_id,
                    "realtor": realtor_id,
                    "proposed": proposed_date,
                    "hours": assignment_window_hours,
                },
            )
        ).one()
        return self._to_row(row)

    async def mark_accepted(self, inspection_id: UUID) -> bool:
        """Accept the assignment: status -> accepted, confirmed_date = proposed.
        Guarded so a second accept (or an expired/non-pending one) is a no-op."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE inspections SET status = 'accepted', "
                    "confirmed_date = proposed_date, updated_at = NOW() "
                    "WHERE id = :id AND status = 'pending' RETURNING id"
                ),
                {"id": inspection_id},
            )
        ).first()
        return row is not None

    @staticmethod
    def _to_row(r: Any) -> InspectionRow:
        return InspectionRow(
            id=r.id,
            transaction_id=r.transaction_id,
            realtor_id=r.realtor_id,
            proposed_date=r.proposed_date,
            confirmed_date=r.confirmed_date,
            status=r.status,
            assignment_expires_at=r.assignment_expires_at,
            created_at=r.created_at,
        )
