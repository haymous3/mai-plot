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


class SellerOfferItem(BaseModel):
    """An offer on the seller's listing (GET /offers — SCRUM-98). The buyer is
    surfaced only as a short reference (contacts stay masked until acceptance,
    per §8)."""

    id: UUID
    listing_id: UUID
    property_title: str
    lga: str
    state: str
    buyer_ref: str
    offered_price_kobo: int
    asking_price_kobo: int
    counter_price_kobo: int | None
    note: str | None
    status: str
    created_at: datetime


class SellerOffersResponse(BaseModel):
    data: list[SellerOfferItem]
