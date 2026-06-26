"""Request/response schemas for buyer deposit checkout (SCRUM-83)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class DepositRequest(BaseModel):
    # Client-generated UUID v4 (CLAUDE.md) — dedupes the payment via
    # UNIQUE(payer_id, idempotency_key).
    idempotency_key: UUID
    amount_kobo: int = Field(gt=0)


class DepositResponse(BaseModel):
    authorization_url: str
    reference: str
    payment_event_id: UUID
