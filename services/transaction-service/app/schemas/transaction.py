"""Request/response models for transaction status transitions (SCRUM-67)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# The only stage values a client may request. Pydantic rejects anything else
# (422 VALIDATION_ERROR) before the state machine even runs — so a client can
# never set an arbitrary stage. Mirrors the transactions.stage CHECK.
TransactionStage = Literal[
    "offer_accepted",
    "inspection_scheduled",
    "inspection_completed",
    "loan_applied",
    "loan_approved",
    "loan_rejected",
    "payment_held",
    "title_held",
    "completed",
    "cancelled",
    "disputed",
    "resolved",
]


class StatusChangeRequest(BaseModel):
    status: TransactionStage


class StatusResponse(BaseModel):
    transaction_id: UUID
    stage: str


class DealItem(BaseModel):
    """A buyer's deal for the "Your Active Deals" list (SCRUM-95)."""

    transaction_id: UUID
    listing_id: UUID
    stage: str
    agreed_price_kobo: int
    property_title: str | None
    sale_type: str | None
    created_at: datetime


class DealsResponse(BaseModel):
    data: list[DealItem]


class SellerDealItem(BaseModel):
    """A seller's transaction for the seller "Transactions" list (SCRUM-98). The
    buyer is masked to a short reference until the deal completes (§8)."""

    transaction_id: UUID
    listing_id: UUID
    buyer_ref: str
    stage: str
    agreed_price_kobo: int
    property_title: str | None
    sale_type: str | None
    created_at: datetime


class SellerDealsResponse(BaseModel):
    data: list[SellerDealItem]
