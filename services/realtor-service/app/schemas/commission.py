"""Schemas for the realtor commission summary (SCRUM-74) + history (SCRUM-140)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.commission_repo import CommissionTotals, RealtorCommissionRow


class CommissionSummaryResponse(BaseModel):
    pending_kobo: int
    available_kobo: int
    withdrawn_kobo: int

    @classmethod
    def from_totals(cls, totals: CommissionTotals) -> CommissionSummaryResponse:
        return cls(
            pending_kobo=totals.pending_kobo,
            available_kobo=totals.available_kobo,
            withdrawn_kobo=totals.withdrawn_kobo,
        )


class CommissionHistoryItem(BaseModel):
    """One commission line in the realtor's Earnings history. amount_kobo is
    BIGINT kobo; status is pending | available | withdrawn."""

    commission_id: UUID
    transaction_id: UUID
    amount_kobo: int
    rate_bps: int
    status: str
    created_at: datetime
    available_at: datetime
    disbursed_at: datetime | None
    property_title: str | None

    @classmethod
    def from_row(cls, row: RealtorCommissionRow) -> CommissionHistoryItem:
        return cls(
            commission_id=row.commission_id,
            transaction_id=row.transaction_id,
            amount_kobo=row.amount_kobo,
            rate_bps=row.rate_bps,
            status=row.status,
            created_at=row.created_at,
            available_at=row.available_at,
            disbursed_at=row.disbursed_at,
            property_title=row.property_title,
        )


class CommissionHistoryResponse(BaseModel):
    data: list[CommissionHistoryItem]

    @classmethod
    def from_rows(cls, rows: list[RealtorCommissionRow]) -> CommissionHistoryResponse:
        return cls(data=[CommissionHistoryItem.from_row(r) for r in rows])
