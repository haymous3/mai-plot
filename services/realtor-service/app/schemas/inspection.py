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


def mask_phone(phone: str | None) -> str | None:
    """A Nigerian MSISDN reduced to a recognisable-but-unusable line for the
    realtor's on-site contact panel — dialling code, stars, last three digits
    (e.g. "+234 *** **** 824"). The full number never leaves the service
    (CLAUDE.md §10). A number too short to mask meaningfully returns None rather
    than leaking most of itself."""
    if phone is None:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 7:
        return None
    prefix = f"+{digits[:3]}" if phone.strip().startswith("+") else digits[:3]
    return f"{prefix} *** **** {digits[-3:]}"


class RealtorInspectionItem(BaseModel):
    """One inspection assigned to the calling realtor, with its property, for the
    realtor portal (SCRUM-140, widened by SCRUM-204).

    Money is BIGINT kobo. The buyer is a short reference only, and the seller is
    a name plus a masked phone — enough to reach the person unlocking the gate,
    never the raw contact details (CLAUDE.md §10)."""

    inspection_id: UUID
    transaction_id: UUID
    status: str
    proposed_date: datetime
    confirmed_date: datetime | None
    assignment_expires_at: datetime
    created_at: datetime
    report_submitted_at: datetime | None
    buyer_ref: str
    inspection_ref: str
    property_title: str | None
    address_text: str | None
    lga: str | None
    state: str | None
    property_type: str | None
    sale_type: str | None
    size_sqm: float | None
    asking_price_kobo: int | None
    cover_photo_url: str | None
    seller_authority_type: str | None
    seller_name: str | None
    seller_phone_masked: str | None

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
            # Same short-reference convention as the seller's offer/deal views.
            buyer_ref=str(row.buyer_id)[:8],
            inspection_ref=str(row.inspection_id)[:8],
            property_title=row.property_title,
            address_text=row.address_text,
            lga=row.lga,
            state=row.state,
            property_type=row.property_type,
            sale_type=row.sale_type,
            size_sqm=float(row.size_sqm) if row.size_sqm is not None else None,
            asking_price_kobo=row.asking_price_kobo,
            cover_photo_url=row.cover_photo_url,
            seller_authority_type=row.seller_authority_type,
            seller_name=row.seller_name,
            seller_phone_masked=mask_phone(row.seller_phone),
        )


class RealtorInspectionsResponse(BaseModel):
    data: list[RealtorInspectionItem]

    @classmethod
    def from_rows(cls, rows: list[RealtorInspectionRow]) -> RealtorInspectionsResponse:
        return cls(data=[RealtorInspectionItem.from_row(r) for r in rows])
