"""Request/response models for transaction status transitions (SCRUM-67)."""

from __future__ import annotations

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
