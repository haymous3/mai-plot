"""Escrow ledger response schemas (SCRUM-69). Money is kobo (BIGINT → int)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LedgerEntry(BaseModel):
    id: UUID
    transaction_id: UUID
    entry_type: str
    amount_kobo: int
    description: str
    payment_event_id: UUID | None
    requires_dual_approval: bool
    approved_by_1: UUID | None
    approved_by_2: UUID | None
    approved_at: datetime | None
    effective: bool
    created_at: datetime


class EscrowLedgerResponse(BaseModel):
    transaction_id: UUID
    balance_kobo: int
    pending_kobo: int
    entries: list[LedgerEntry]


class ApproveResponse(BaseModel):
    payment_event_id: UUID
    status: str
    approved_entry_ids: list[UUID]
