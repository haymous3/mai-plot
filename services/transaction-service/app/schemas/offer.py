"""Request/response models for the offer flow (SCRUM-66)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateOfferRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    listing_id: UUID
    amount_kobo: int = Field(gt=0)


class CounterRequest(BaseModel):
    counter_amount_kobo: int = Field(gt=0)


class RespondRequest(BaseModel):
    action: Literal["accept", "reject"]


class OfferResponse(BaseModel):
    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID
    status: str
    amount_kobo: int
    counter_amount_kobo: int | None
    expires_at: datetime
    transaction_id: UUID | None
