"""Schemas for inspection requests (SCRUM-72)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.inspection_repo import AssignedRealtorRow, InspectionRow


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


class AssignedRealtorResponse(BaseModel):
    """The realtor a party sees on their transaction view (SCRUM-139).
    `assigned` is False when no inspection has been requested yet; identity
    fields are never contact details (masking, CLAUDE.md §10)."""

    assigned: bool
    inspection_id: UUID | None = None
    realtor_name: str | None = None
    esvarbon_number: str | None = None
    status: str | None = None
    proposed_date: datetime | None = None
    confirmed_date: datetime | None = None

    @classmethod
    def none(cls) -> AssignedRealtorResponse:
        return cls(assigned=False)

    @classmethod
    def from_row(cls, row: AssignedRealtorRow) -> AssignedRealtorResponse:
        return cls(
            assigned=True,
            inspection_id=row.inspection_id,
            realtor_name=row.realtor_name,
            esvarbon_number=row.esvarbon_number,
            status=row.status,
            proposed_date=row.proposed_date,
            confirmed_date=row.confirmed_date,
        )
