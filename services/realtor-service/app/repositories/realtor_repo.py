"""Access to the realtors table (owned by realtor-service, SCRUM-71).

The realtors row extends users(id) with ESVARBON licence, coverage areas, the
private government-ID object key, and the approval lifecycle
(pending -> approved | rejected | suspended).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
        esvarbon_number: str,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        government_id_s3_key: str,
    ) -> RealtorRow:
        """Insert a fresh realtor profile at approval_status='pending'."""
        row = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO realtors
                        (id, esvarbon_number, years_of_experience, coverage_states,
                         coverage_lgas, government_id_s3_key, approval_status)
                    VALUES
                        (:id, :esvarbon, :years, :states, :lgas, :key, 'pending')
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "id": user_id,
                    "esvarbon": esvarbon_number,
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
        esvarbon_number: str,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        government_id_s3_key: str,
    ) -> RealtorRow:
        """Re-apply after a rejection — overwrite the profile + reset to pending,
        clearing the prior decision."""
        row = (
            await self._session.execute(
                text(
                    f"""
                    UPDATE realtors SET
                        esvarbon_number = :esvarbon,
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
                    "esvarbon": esvarbon_number,
                    "years": years_of_experience,
                    "states": coverage_states,
                    "lgas": coverage_lgas,
                    "key": government_id_s3_key,
                },
            )
        ).one()
        return self._to_row(row)

    async def list_pending(self, *, limit: int = 100) -> list[RealtorRow]:
        rows = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM realtors WHERE approval_status = 'pending' "
                    "ORDER BY created_at ASC LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).all()
        return [self._to_row(r) for r in rows]

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
