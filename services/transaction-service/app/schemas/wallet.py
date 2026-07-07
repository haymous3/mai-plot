"""Response models for the read-only buyer wallet (SCRUM-95)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ActivePaymentOut(BaseModel):
    transaction_id: UUID
    listing_id: UUID
    property_title: str | None
    paid_kobo: int
    total_kobo: int
    stage: str


class WalletSummaryOut(BaseModel):
    in_escrow_kobo: int
    escrow_deal_count: int
    total_invested_kobo: int
    active_property_count: int
    active_payments: list[ActivePaymentOut]


class PaymentOut(BaseModel):
    id: UUID
    payment_type: str
    amount_kobo: int
    status: str
    provider: str
    provider_reference: str | None
    transaction_id: UUID | None
    property_title: str | None
    created_at: datetime


class PaymentsOut(BaseModel):
    data: list[PaymentOut]
