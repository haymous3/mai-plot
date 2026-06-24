"""Unit tests for CommissionService (SCRUM-74)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.commission_repo import CommissionAccrual, CommissionTotals
from app.services.commission_service import CommissionService, compute_commission_kobo

pytestmark = pytest.mark.asyncio


async def test_compute_commission_floor() -> None:
    # async only to satisfy the module-level asyncio mark — no await needed.
    # 2% of ₦50,000,000 (5_000_000_000 kobo) = 100_000_000 kobo.
    assert compute_commission_kobo(5_000_000_000, rate_bps=200) == 100_000_000
    # Floor: 2% of 12,345 kobo = 246.9 -> 246.
    assert compute_commission_kobo(12_345, rate_bps=200) == 246


class _StubCommissionRepo:
    def __init__(self, *, accruable: list[CommissionAccrual], create_returns: bool = True) -> None:
        self._accruable = accruable
        self._create_returns = create_returns
        self.created: list[dict[str, object]] = []
        self.released = 0

    async def list_accruable(self, *, limit: int = 500) -> list[CommissionAccrual]:
        return self._accruable

    async def create(
        self,
        *,
        realtor_id: UUID,
        transaction_id: UUID,
        inspection_id: UUID,
        amount_kobo: int,
        rate_bps: int,
        available_at: datetime,
    ) -> bool:
        self.created.append({"realtor_id": realtor_id, "amount_kobo": amount_kobo})
        return self._create_returns

    async def release_due(self) -> int:
        self.released = 2
        return 2

    async def totals_for_realtor(self, realtor_id: UUID) -> CommissionTotals:
        return CommissionTotals(pending_kobo=100, available_kobo=50, withdrawn_kobo=0)


def _accrual(price: int = 5_000_000_000) -> CommissionAccrual:
    return CommissionAccrual(
        transaction_id=uuid4(),
        inspection_id=uuid4(),
        realtor_id=uuid4(),
        agreed_price_kobo=price,
    )


def _service(repo: _StubCommissionRepo) -> CommissionService:
    return CommissionService(
        commissions=repo,  # type: ignore[arg-type]
        rate_bps=200,
        available_business_days=3,
    )


async def test_accrue_records_each_new_deal() -> None:
    repo = _StubCommissionRepo(accruable=[_accrual(), _accrual()])
    result = await _service(repo).accrue()

    assert result.recorded == 2
    assert result.released == 2
    assert repo.created[0]["amount_kobo"] == 100_000_000


async def test_accrue_skips_already_recorded() -> None:
    # create returns False (ON CONFLICT) -> nothing counted as recorded.
    repo = _StubCommissionRepo(accruable=[_accrual()], create_returns=False)
    result = await _service(repo).accrue()
    assert result.recorded == 0


async def test_summary_returns_totals() -> None:
    repo = _StubCommissionRepo(accruable=[])
    totals = await _service(repo).summary(uuid4())
    assert totals.pending_kobo == 100
    assert totals.available_kobo == 50
