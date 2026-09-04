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


def _blank_to_none(value: str | None) -> str | None:
    """A whitespace-only joined name/phone reads as "no value" to the caller."""
    return value if value and value.strip() else None


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


@dataclass(frozen=True)
class AssignedRealtorRow:
    """The realtor assigned to a transaction's (latest) inspection, with the
    non-contact identity a party is allowed to see (SCRUM-139). Name + licence +
    inspection status only — never phone/email (contact masking, CLAUDE.md §10)."""

    inspection_id: UUID
    realtor_id: UUID
    realtor_name: str | None
    esvarbon_number: str | None
    status: str
    proposed_date: datetime
    confirmed_date: datetime | None


@dataclass(frozen=True)
class RealtorInspectionRow:
    """An inspection assigned to a realtor, joined with its property, for the
    realtor portal's dashboard + assigned-inspections list (SCRUM-140, widened by
    SCRUM-204 for the designed inspection cards).

    `seller_phone` is raw PII read straight from user_pii — the schema layer masks
    it to the last three digits before it leaves the service, and it must never be
    logged. The realtor sees the seller's name + a masked line only because they
    need site access on an assignment they have accepted (CLAUDE.md §10)."""

    inspection_id: UUID
    transaction_id: UUID
    status: str
    proposed_date: datetime
    confirmed_date: datetime | None
    assignment_expires_at: datetime
    created_at: datetime
    report_submitted_at: datetime | None
    buyer_id: UUID
    property_title: str | None
    address_text: str | None
    lga: str | None
    state: str | None
    property_type: str | None
    sale_type: str | None
    size_sqm: Decimal | None
    asking_price_kobo: int | None
    cover_photo_url: str | None
    seller_authority_type: str | None
    seller_name: str | None
    seller_phone: str | None


@dataclass(frozen=True)
class LapsedInspection:
    """A pending inspection whose acceptance window has lapsed, with the data the
    reassignment sweep needs (SCRUM-123)."""

    inspection_id: UUID
    realtor_id: UUID
    listing_id: UUID
    declined_realtor_ids: list[UUID]


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

    async def latest_assignment_for_transaction(
        self, transaction_id: UUID
    ) -> AssignedRealtorRow | None:
        """The most recent inspection on a transaction, joined to the assigned
        realtor's display name (user_pii) + ESVARBON licence (realtors) — for the
        seller/buyer "who's inspecting" view (SCRUM-139). None if never assigned.
        Returns identity only, no contact details."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT i.id AS inspection_id, i.realtor_id, i.status,
                           i.proposed_date, i.confirmed_date,
                           p.full_name AS realtor_name, r.esvarbon_number
                    FROM inspections i
                    LEFT JOIN user_pii p ON p.user_id = i.realtor_id
                    LEFT JOIN realtors r ON r.id = i.realtor_id
                    WHERE i.transaction_id = :tx
                    ORDER BY i.created_at DESC
                    LIMIT 1
                    """
                ),
                {"tx": transaction_id},
            )
        ).first()
        if row is None:
            return None
        name = _blank_to_none(row.realtor_name)
        return AssignedRealtorRow(
            inspection_id=row.inspection_id,
            realtor_id=row.realtor_id,
            realtor_name=name,
            esvarbon_number=row.esvarbon_number,
            status=row.status,
            proposed_date=row.proposed_date,
            confirmed_date=row.confirmed_date,
        )

    async def list_for_realtor(
        self, realtor_id: UUID, *, limit: int = 100
    ) -> list[RealtorInspectionRow]:
        """Every inspection assigned to a realtor, newest first, joined to its
        property and the seller the realtor meets on site — the realtor portal's
        dashboard, assigned-inspections table and report header (SCRUM-140,
        widened by SCRUM-204).

        The cover photo is the listing's first photo by sort_order, picked by a
        LATERAL so one listing's many media rows can't fan the result out;
        idx_media_listing(listing_id, sort_order) serves it. The seller join is
        via transactions.seller_id (the deal's seller), not the listing owner."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT i.id AS inspection_id, i.transaction_id, i.status,
                           i.proposed_date, i.confirmed_date, i.assignment_expires_at,
                           i.created_at, i.report_submitted_at, t.buyer_id,
                           pl.title AS property_title, pl.address_text, pl.lga, pl.state,
                           pl.property_type, pl.sale_type, pl.size_sqm, pl.asking_price_kobo,
                           cover.cdn_url AS cover_photo_url,
                           su.seller_authority_type,
                           sp.full_name AS seller_name, sp.phone AS seller_phone
                    FROM inspections i
                    JOIN transactions t ON t.id = i.transaction_id
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    LEFT JOIN LATERAL (
                        SELECT m.cdn_url
                        FROM listing_media m
                        WHERE m.listing_id = t.listing_id AND m.media_type = 'photo'
                        ORDER BY m.sort_order, m.created_at
                        LIMIT 1
                    ) cover ON TRUE
                    LEFT JOIN users su ON su.id = t.seller_id
                    LEFT JOIN user_pii sp ON sp.user_id = t.seller_id
                    WHERE i.realtor_id = :realtor
                    ORDER BY i.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"realtor": realtor_id, "limit": limit},
            )
        ).all()
        return [
            RealtorInspectionRow(
                inspection_id=r.inspection_id,
                transaction_id=r.transaction_id,
                status=r.status,
                proposed_date=r.proposed_date,
                confirmed_date=r.confirmed_date,
                assignment_expires_at=r.assignment_expires_at,
                created_at=r.created_at,
                report_submitted_at=r.report_submitted_at,
                buyer_id=r.buyer_id,
                property_title=r.property_title,
                address_text=r.address_text,
                lga=r.lga,
                state=r.state,
                property_type=r.property_type,
                sale_type=r.sale_type,
                size_sqm=r.size_sqm,
                asking_price_kobo=r.asking_price_kobo,
                cover_photo_url=r.cover_photo_url,
                seller_authority_type=r.seller_authority_type,
                seller_name=_blank_to_none(r.seller_name),
                seller_phone=_blank_to_none(r.seller_phone),
            )
            for r in rows
        ]

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

    async def mark_rescheduled(self, inspection_id: UUID, *, new_date: datetime) -> bool:
        """Propose an alternate time (SCRUM-141): status -> rescheduled with the new
        proposed_date, and confirmed_date set to it (a reschedule commits the
        realtor to the new time — the accept-with-new-time model). Guarded on
        status='pending' so it mirrors the accept window; a second call is a no-op."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE inspections SET status = 'rescheduled', "
                    "proposed_date = :new, confirmed_date = :new, updated_at = NOW() "
                    "WHERE id = :id AND status = 'pending' RETURNING id"
                ),
                {"id": inspection_id, "new": new_date},
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
        report_data persisted. Guarded on status in ('accepted','rescheduled') so
        it can only be submitted once, on a confirmed inspection (a rescheduled one
        is confirmed at the new time — SCRUM-141)."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE inspections SET status = 'completed', "
                    "report_submitted_at = NOW(), gps_lat = :lat, gps_lng = :lng, "
                    "report_data = CAST(:data AS jsonb), updated_at = NOW() "
                    "WHERE id = :id AND status IN ('accepted', 'rescheduled') RETURNING id"
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

    async def list_lapsed_pending(self, *, limit: int = 500) -> list[LapsedInspection]:
        """Pending inspections whose acceptance window has elapsed, with the
        listing (for proximity) + who has already declined/lapsed (SCRUM-123)."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT i.id, i.realtor_id, t.listing_id, i.declined_realtor_ids
                    FROM inspections i
                    JOIN transactions t ON t.id = i.transaction_id
                    WHERE i.status = 'pending' AND i.assignment_expires_at <= NOW()
                    ORDER BY i.assignment_expires_at ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).all()
        return [
            LapsedInspection(
                inspection_id=r.id,
                realtor_id=r.realtor_id,
                listing_id=r.listing_id,
                declined_realtor_ids=list(r.declined_realtor_ids or []),
            )
            for r in rows
        ]

    async def reassign(
        self, inspection_id: UUID, *, old_realtor_id: UUID, new_realtor_id: UUID, window_hours: int
    ) -> bool:
        """Reassign a lapsed pending inspection to a new realtor: reset the
        acceptance window and record the old realtor in declined_realtor_ids so
        they're never re-offered it. Guarded on status='pending'."""
        row = (
            await self._session.execute(
                text(
                    """
                    UPDATE inspections SET
                        realtor_id = :new,
                        assignment_expires_at = NOW() + make_interval(hours => :hours),
                        declined_realtor_ids = array_append(declined_realtor_ids, :old),
                        updated_at = NOW()
                    WHERE id = :id AND status = 'pending'
                    RETURNING id
                    """
                ),
                {
                    "id": inspection_id,
                    "new": new_realtor_id,
                    "old": old_realtor_id,
                    "hours": window_hours,
                },
            )
        ).first()
        return row is not None

    async def defer_assignment(self, inspection_id: UUID, *, hours: int) -> bool:
        """Push the acceptance window out (no realtor available now) so the sweep
        doesn't re-process it every tick. The current realtor stays assigned."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE inspections SET "
                    "assignment_expires_at = NOW() + make_interval(hours => :hours), "
                    "updated_at = NOW() WHERE id = :id AND status = 'pending' RETURNING id"
                ),
                {"id": inspection_id, "hours": hours},
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
