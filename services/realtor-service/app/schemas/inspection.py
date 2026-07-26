"""Schemas for inspection requests (SCRUM-72)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.inspection_repo import (
    AssignedRealtorRow,
    InspectionRow,
    RealtorInspectionRow,
)


class InspectionRequest(BaseModel):
    transaction_id: UUID
    proposed_date: datetime


class ProposeTimeRequest(BaseModel):
    """The realtor's proposed alternate inspection time (SCRUM-141)."""

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


class RealtorInspectionItem(BaseModel):
    """One inspection assigned to the calling realtor, with its property, for the
    realtor portal (SCRUM-140)."""

    inspection_id: UUID
    transaction_id: UUID
    status: str
    proposed_date: datetime
    confirmed_date: datetime | None
    assignment_expires_at: datetime
    created_at: datetime
    report_submitted_at: datetime | None
    property_title: str | None
    address_text: str | None
    lga: str | None
    state: str | None

    @classmethod
    def from_row(cls, row: RealtorInspectionRow) -> RealtorInspectionItem:
        return cls(
            inspection_id=row.inspection_id,
            transaction_id=row.transaction_id,
            status=row.status,
            proposed_date=row.proposed_date,
            confirmed_date=row.confirmed_date,
            assignment_expires_at=row.assignment_expires_at,
            created_at=row.created_at,
            report_submitted_at=row.report_submitted_at,
            property_title=row.property_title,
            address_text=row.address_text,
            lga=row.lga,
            state=row.state,
        )


class RealtorInspectionsResponse(BaseModel):
    data: list[RealtorInspectionItem]

    @classmethod
    def from_rows(cls, rows: list[RealtorInspectionRow]) -> RealtorInspectionsResponse:
        return cls(data=[RealtorInspectionItem.from_row(r) for r in rows])
