"""Access to the realtors table (owned by realtor-service, SCRUM-71).

The realtors row extends users(id) with coverage areas, the private
government-ID object key, and the approval lifecycle
(pending -> approved | rejected | suspended).

`esvarbon_number` is no longer written (SCRUM-207): a realtor is verified by
admin review and issued a Maihomme registration number instead. The column is
still READ, because realtors onboarded before the change have one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PendingRealtorRow:
    """One pending application for the admin review queue (SCRUM-207).

    Carries `full_name` from user_pii, which RealtorRow does not. Before
    SCRUM-207 the queue's only identifying column was the ESVARBON licence
    number — with that no longer collected, an admin would have been approving
    anonymous rows, so the applicant's name is read here.
    """

    id: UUID
    full_name: str | None
    esvarbon_number: str | None
    years_of_experience: int | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    created_at: datetime


@dataclass(frozen=True)
class RealtorRow:
    id: UUID
    esvarbon_number: str | None
    years_of_experience: int | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    completed_deals: int
    approval_status: str
    government_id_s3_key: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    suspension_reason: str | None
    created_at: datetime


_COLUMNS = (
    "id, esvarbon_number, years_of_experience, coverage_states, coverage_lgas, "
    "completed_deals, approval_status, government_id_s3_key, approved_by, "
    "approved_at, suspension_reason, created_at"
)


class RealtorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> RealtorRow | None:
        row = (
            await self._session.execute(
                text(f"SELECT {_COLUMNS} FROM realtors WHERE id = :id"),
                {"id": user_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def create(
        self,
        *,
        user_id: UUID,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        government_id_s3_key: str,
    ) -> RealtorRow:
        """Insert a fresh realtor profile at approval_status='pending'.

        esvarbon_number is left to its NULL default (SCRUM-207). The column is
        UNIQUE, and Postgres allows any number of NULLs in a unique index, so
        every realtor from here on coexists happily.
        """
        row = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO realtors
                        (id, years_of_experience, coverage_states,
                         coverage_lgas, government_id_s3_key, approval_status)
                    VALUES
                        (:id, :years, :states, :lgas, :key, 'pending')
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "id": user_id,
                    "years": years_of_experience,
                    "states": coverage_states,
                    "lgas": coverage_lgas,
                    "key": government_id_s3_key,
                },
            )
        ).one()
        return self._to_row(row)

    async def resubmit(
        self,
        *,
        user_id: UUID,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        government_id_s3_key: str,
    ) -> RealtorRow:
        """Re-apply after a rejection — overwrite the profile + reset to pending,
        clearing the prior decision.

        Deliberately does NOT clear esvarbon_number. A realtor who supplied one
        before SCRUM-207 keeps it on a re-submission: the field is no longer
        collected, and blanking it here would delete a licence number the
        platform was given, on a path that has nothing to do with it.
        """
        row = (
            await self._session.execute(
                text(
                    f"""
                    UPDATE realtors SET
                        years_of_experience = :years,
                        coverage_states = :states,
                        coverage_lgas = :lgas,
                        government_id_s3_key = :key,
                        approval_status = 'pending',
                        approved_by = NULL,
                        approved_at = NULL,
                        suspension_reason = NULL,
                        updated_at = NOW()
                    WHERE id = :id
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "id": user_id,
                    "years": years_of_experience,
                    "states": coverage_states,
                    "lgas": coverage_lgas,
                    "key": government_id_s3_key,
                },
            )
        ).one()
        return self._to_row(row)

    async def list_pending(self, *, limit: int = 100) -> list[PendingRealtorRow]:
        """Pending applications, oldest first, with the applicant's name.

        LEFT JOIN, not JOIN: a realtor whose user_pii row is missing must still
        appear in the queue. Dropping an application off the review list because
        one column is absent hides work rather than surfacing it.
        """
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT r.id, p.full_name, r.esvarbon_number, r.years_of_experience,
                           r.coverage_states, r.coverage_lgas, r.created_at
                    FROM realtors r
                    LEFT JOIN user_pii p ON p.user_id = r.id
                    WHERE r.approval_status = 'pending'
                    ORDER BY r.created_at ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).all()
        return [
            PendingRealtorRow(
                id=r.id,
                full_name=r.full_name,
                esvarbon_number=r.esvarbon_number,
                years_of_experience=r.years_of_experience,
                coverage_states=list(r.coverage_states),
                coverage_lgas=list(r.coverage_lgas),
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def set_decision(
        self,
        *,
        user_id: UUID,
        status: str,
        approved_by: UUID,
        suspension_reason: str | None,
    ) -> bool:
        """Apply an approve/reject/suspend decision. approved_at + approved_by are
        stamped for every decision (who/when reviewed). Returns False if the row
        is gone."""
        row = (
            await self._session.execute(
                text(
                    """
                    UPDATE realtors SET
                        approval_status = :status,
                        approved_by = :by,
                        approved_at = NOW(),
                        suspension_reason = :reason,
                        updated_at = NOW()
                    WHERE id = :id
                    RETURNING id
                    """
                ),
                {"id": user_id, "status": status, "by": approved_by, "reason": suspension_reason},
            )
        ).first()
        return row is not None

    async def set_base_location(self, user_id: UUID, *, lat: float, lng: float) -> None:
        """Set the realtor's base geolocation (SCRUM-72) used by auto-assignment."""
        await self._session.execute(
            text(
                "UPDATE realtors SET "
                "base_location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"id": user_id, "lat": lat, "lng": lng},
        )

    async def find_nearest_approved(
        self, *, listing_id: UUID, radius_m: float, exclude: list[UUID] | None = None
    ) -> UUID | None:
        """The nearest approved realtor (with a base_location) within `radius_m` of
        the listing's property point, excluding any given ids. None if nobody is
        in range (the assignment caller treats that as the admin-fallback case)."""
        params: dict[str, object] = {"listing_id": listing_id, "radius": radius_m}
        exclude_clause = ""
        for i, rid in enumerate(exclude or []):
            params[f"e{i}"] = rid
            exclude_clause += f" AND r.id <> :e{i}"
        row = (
            await self._session.execute(
                text(
                    f"""
                    SELECT r.id
                    FROM realtors r,
                         (SELECT location FROM property_listings
                          WHERE id = :listing_id AND deleted_at IS NULL) pl
                    WHERE r.approval_status = 'approved'
                      AND r.base_location IS NOT NULL
                      AND ST_DWithin(r.base_location, pl.location, :radius)
                      {exclude_clause}
                    ORDER BY ST_Distance(r.base_location, pl.location) ASC
                    LIMIT 1
                    """
                ),
                params,
            )
        ).first()
        return row.id if row is not None else None

    @staticmethod
    def _to_row(r: Any) -> RealtorRow:
        return RealtorRow(
            id=r.id,
            esvarbon_number=r.esvarbon_number,
            years_of_experience=r.years_of_experience,
            coverage_states=list(r.coverage_states or []),
            coverage_lgas=list(r.coverage_lgas or []),
            completed_deals=r.completed_deals,
            approval_status=r.approval_status,
            government_id_s3_key=r.government_id_s3_key,
            approved_by=r.approved_by,
            approved_at=r.approved_at,
            suspension_reason=r.suspension_reason,
            created_at=r.created_at,
        )
