"""Request/response models for the legal-team admin endpoints (SCRUM-56)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PoaQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    owner_name: str | None
    submitted_at: datetime


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class PoaQueueResponse(BaseModel):
    items: list[PoaQueueItem]
    pagination: Pagination


class PoaReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    # Required only for a rejection — enforced in the service so the 422 carries
    # the POA_REASON_REQUIRED code rather than a generic validation error.
    reason: str | None = None


class PoaReviewResponse(BaseModel):
    user_id: UUID
    poa_verified_status: str
