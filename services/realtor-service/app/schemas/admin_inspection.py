"""Schemas for admin inspection placement (SCRUM-208)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.repositories.inspection_repo import InspectionRow, UnassignedInspectionRow
from app.repositories.realtor_repo import ApprovedRealtorRow


class UnassignedInspectionItem(BaseModel):
    """One request waiting for a realtor.

    Deliberately identity-light: buyer and seller appear as short reference
    strings, not names or contacts. An admin placing work needs to know WHICH
    property and WHEN, not who the parties are — and CLAUDE.md §10 masks the
    parties from everyone but each other until a deal is accepted.
    """

    id: UUID
    transaction_id: UUID
    proposed_date: datetime
    created_at: datetime
    listing_id: UUID
    property_title: str | None
    lga: str | None
    state: str | None
    buyer_ref: str
    seller_ref: str
    # False = the listing row is missing or soft-deleted, so proximity assignment
    # can never place this request. Surfaced so an admin knows the sweep will
    # never get to it and a manual placement is the only route.
    property_located: bool

    @classmethod
    def from_row(cls, row: UnassignedInspectionRow) -> UnassignedInspectionItem:
        return cls(
            id=row.id,
            transaction_id=row.transaction_id,
            proposed_date=row.proposed_date,
            created_at=row.created_at,
            listing_id=row.listing_id,
            property_title=row.property_title,
            lga=row.lga,
            state=row.state,
            buyer_ref=str(row.buyer_id)[:8],
            seller_ref=str(row.seller_id)[:8],
            property_located=row.property_located,
        )


class UnassignedInspectionsResponse(BaseModel):
    items: list[UnassignedInspectionItem]


class AssignableRealtorItem(BaseModel):
    """One approved realtor an admin may place work with."""

    id: UUID
    full_name: str | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    completed_deals: int
    # False = unreachable by proximity assignment, which is currently EVERY
    # realtor who onboarded through the product (no location is collected). The
    # UI says so, because otherwise "why did nobody get auto-assigned" has no
    # visible answer.
    has_base_location: bool

    @classmethod
    def from_row(cls, row: ApprovedRealtorRow) -> AssignableRealtorItem:
        return cls(
            id=row.id,
            full_name=row.full_name,
            coverage_states=row.coverage_states,
            coverage_lgas=row.coverage_lgas,
            completed_deals=row.completed_deals,
            has_base_location=row.has_base_location,
        )


class AssignableRealtorsResponse(BaseModel):
    items: list[AssignableRealtorItem]


class PlaceInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    realtor_id: UUID


class AdminCreateInspectionRequest(BaseModel):
    """Create an inspection on the admin's authority.

    `realtor_id` omitted = try proximity, and fail loudly if nobody is in range;
    the admin asked us to choose, so silently parking the row would answer a
    question they did not ask.
    """

    model_config = ConfigDict(extra="ignore")

    transaction_id: UUID
    proposed_date: datetime
    realtor_id: UUID | None = Field(default=None)


class AdminInspectionResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    realtor_id: UUID | None
    status: str
    proposed_date: datetime
    assignment_expires_at: datetime | None
    # True when proximity chose the realtor, false when the admin named them.
    auto_assigned: bool = False

    @classmethod
    def from_row(
        cls, row: InspectionRow, *, auto_assigned: bool = False
    ) -> AdminInspectionResponse:
        return cls(
            id=row.id,
            transaction_id=row.transaction_id,
            realtor_id=row.realtor_id,
            status=row.status,
            proposed_date=row.proposed_date,
            assignment_expires_at=row.assignment_expires_at,
            auto_assigned=auto_assigned,
        )
