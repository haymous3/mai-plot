"""Schemas for inspection requests (SCRUM-72)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.inspection_repo import InspectionRow


class InspectionRequest(BaseModel):
    transaction_id: UUID
    proposed_date: datetime


class InspectionResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    realtor_id: UUID
    proposed_date: datetime
    confirmed_date: datetime | None
    status: str
    assignment_expires_at: datetime

    @classmethod
    def from_row(cls, row: InspectionRow) -> InspectionResponse:
        return cls(
            id=row.id,
            transaction_id=row.transaction_id,
            realtor_id=row.realtor_id,
            proposed_date=row.proposed_date,
            confirmed_date=row.confirmed_date,
            status=row.status,
            assignment_expires_at=row.assignment_expires_at,
        )
