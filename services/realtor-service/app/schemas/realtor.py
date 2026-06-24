"""Response/request schemas for realtor onboarding + review (SCRUM-71).

Registration is multipart (the government-ID file + form fields), so its inputs
are Form() params on the route, not a JSON body model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.repositories.realtor_repo import RealtorRow


class RealtorProfile(BaseModel):
    id: UUID
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


class RealtorQueueItem(BaseModel):
    id: UUID
    esvarbon_number: str | None
    years_of_experience: int | None
    coverage_states: list[str]
    coverage_lgas: list[str]
    created_at: datetime

    @classmethod
    def from_row(cls, row: RealtorRow) -> RealtorQueueItem:
        return cls(
            id=row.id,
            esvarbon_number=row.esvarbon_number,
            years_of_experience=row.years_of_experience,
            coverage_states=row.coverage_states,
            coverage_lgas=row.coverage_lgas,
            created_at=row.created_at,
        )


class RealtorQueueResponse(BaseModel):
    items: list[RealtorQueueItem]
