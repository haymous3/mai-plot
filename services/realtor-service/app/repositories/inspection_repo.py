"""Access to the inspections table (owned by realtor-service, SCRUM-72).

An inspection is created already assigned to the nearest approved realtor, with a
2-hour acceptance window (assignment_expires_at). The realtor accepts within the
window; a lapsed window is reassigned by a follow-up sweep.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    gps_lat: Decimal | None
    gps_lng: Decimal | None
    report_submitted_at: datetime | None
    report_data: dict[str, Any] | None


_COLUMNS = (
    "id, transaction_id, realtor_id, proposed_date, confirmed_date, status, "
    "assignment_expires_at, created_at, gps_lat, gps_lng, report_submitted_at, report_data"
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

    async def submit_report(
        self,
        inspection_id: UUID,
        *,
        gps_lat: float,
        gps_lng: float,
        report_data: dict[str, Any],
    ) -> bool:
        """Store the report: status -> completed, report_submitted_at = now, GPS +
        report_data persisted. Guarded on status='accepted' so it can only be
        submitted once, on a confirmed inspection."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE inspections SET status = 'completed', "
                    "report_submitted_at = NOW(), gps_lat = :lat, gps_lng = :lng, "
                    "report_data = CAST(:data AS jsonb), updated_at = NOW() "
                    "WHERE id = :id AND status = 'accepted' RETURNING id"
                ),
                {
                    "id": inspection_id,
                    "lat": gps_lat,
                    "lng": gps_lng,
                    "data": json.dumps(report_data),
                },
            )
        ).first()
        return row is not None

    async def is_point_within_property(
        self, *, listing_id: UUID, lat: float, lng: float, meters: float
    ) -> bool:
        """Whether (lat,lng) is within `meters` of the listing's property point —
        the GPS validation for report submission (AC: within 1km)."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT ST_DWithin(
                        location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :meters
                    ) AS within
                    FROM property_listings WHERE id = :listing_id AND deleted_at IS NULL
                    """
                ),
                {"listing_id": listing_id, "lat": lat, "lng": lng, "meters": meters},
            )
        ).first()
        return bool(row.within) if row is not None else False

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
            gps_lat=r.gps_lat,
            gps_lng=r.gps_lng,
            report_submitted_at=r.report_submitted_at,
            report_data=r.report_data,
        )
