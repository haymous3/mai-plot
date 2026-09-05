"""Response/request schemas for realtor onboarding + review (SCRUM-71).

Registration is multipart (the government-ID file + form fields), so its inputs
are Form() params on the route, not a JSON body model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.repositories.realtor_repo import PendingRealtorRow, RealtorRow


class RealtorProfile(BaseModel):
    id: UUID
    # No longer collected (SCRUM-207) — null for every realtor onboarded from
    # here on, populated for those who supplied one before. Kept on the response
    # so the historic value is not lost to the API.
    esvarbon_number: str | None
    years_of_experience: int | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    completed_deals: int
    approval_status: str

    @classmethod
    def from_row(cls, row: RealtorRow) -> RealtorProfile:
        return cls(
            id=row.id,
            esvarbon_number=row.esvarbon_number,
            years_of_experience=row.years_of_experience,
            coverage_states=row.coverage_states,
            coverage_lgas=row.coverage_lgas,
            completed_deals=row.completed_deals,
            approval_status=row.approval_status,
        )


class RealtorReviewRequest(BaseModel):
    action: Literal["approve", "reject", "suspend"]
    reason: str | None = None


class RealtorReviewResponse(BaseModel):
    id: UUID
    approval_status: str
    # Set on approval only (SCRUM-207). Surfaced so the reviewer can read the
    # number back to the realtor if the email never arrives — nothing else in the
    # admin surface can show it, and the realtor cannot sign in without it.
    registration_number: str | None = None


class RealtorQueueItem(BaseModel):
    id: UUID
    # The applicant's name (SCRUM-207). Added because ESVARBON — until now the
    # queue's only identifying column — is no longer collected.
    full_name: str | None
    # Kept for the realtors who supplied one before SCRUM-207; null from here on.
    esvarbon_number: str | None
    years_of_experience: int | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    created_at: datetime

    @classmethod
    def from_row(cls, row: PendingRealtorRow) -> RealtorQueueItem:
        return cls(
            id=row.id,
            full_name=row.full_name,
            esvarbon_number=row.esvarbon_number,
            years_of_experience=row.years_of_experience,
            coverage_states=row.coverage_states,
            coverage_lgas=row.coverage_lgas,
            created_at=row.created_at,
        )


class RealtorQueueResponse(BaseModel):
    items: list[RealtorQueueItem]


class GovernmentIdUrlResponse(BaseModel):
    """A short-TTL pre-signed URL for a realtor's uploaded ID document."""

    url: str
