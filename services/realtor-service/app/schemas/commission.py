"""Schemas for the realtor commission summary (SCRUM-74)."""

from __future__ import annotations

from pydantic import BaseModel

from app.repositories.commission_repo import CommissionTotals


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
