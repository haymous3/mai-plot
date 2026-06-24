"""Realtor commission accrual + release (SCRUM-74).

On a completed deal, the realtor who did the inspection accrues a commission =
rate_bps/10_000 of the agreed price (floor division, BIGINT kobo, favours the
platform by a sub-kobo). It's held 'pending' for N business days, then released
to 'available'. The Celery beat calls `accrue()`; the realtor dashboard reads
`summary()`. NO money moves here — the escrow debit + disbursement are M3 /
SCRUM-86.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.repositories.commission_repo import CommissionRepository, CommissionTotals
from app.services.business_days import add_business_days

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccrualResult:
    recorded: int
    released: int


def compute_commission_kobo(agreed_price_kobo: int, *, rate_bps: int) -> int:
    """Floor-rounded commission in kobo. Floor keeps it integer + favours the
    platform (the realtor is never over-paid by rounding)."""
    return agreed_price_kobo * rate_bps // 10_000


class CommissionService:
    def __init__(
        self,
        *,
        commissions: CommissionRepository,
        rate_bps: int,
        available_business_days: int,
    ) -> None:
        self._commissions = commissions
        self._rate_bps = rate_bps
        self._available_business_days = available_business_days

    async def accrue(self) -> AccrualResult:
        """Record commissions for newly-completed deals, then release any whose
        hold has elapsed. Idempotent — re-running records nothing new."""
        now = datetime.now(UTC)
        available_at = add_business_days(now, self._available_business_days)

        recorded = 0
        for deal in await self._commissions.list_accruable():
            amount = compute_commission_kobo(deal.agreed_price_kobo, rate_bps=self._rate_bps)
            inserted = await self._commissions.create(
                realtor_id=deal.realtor_id,
                transaction_id=deal.transaction_id,
                inspection_id=deal.inspection_id,
                amount_kobo=amount,
                rate_bps=self._rate_bps,
                available_at=available_at,
            )
            if inserted:
                recorded += 1

        released = await self._commissions.release_due()
        logger.info("commission.accrual.run", extra={"recorded": recorded, "released": released})
        return AccrualResult(recorded=recorded, released=released)

    async def summary(self, realtor_id: UUID) -> CommissionTotals:
        return await self._commissions.totals_for_realtor(realtor_id)
