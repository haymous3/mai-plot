"""Unit tests for LoanQueryService (SCRUM-94)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.loan_repo import LoanDetailRow
from app.security import CurrentUser
from app.services.loan_query import LoanNotFound, LoanQueryService, NotLoanViewer

pytestmark = pytest.mark.asyncio

_BUYER = uuid4()


def _detail(*, buyer: UUID = _BUYER) -> LoanDetailRow:
    return LoanDetailRow(
        id=uuid4(),
        buyer_id=buyer,
        transaction_id=uuid4(),
        status="approved",
        requested_amount_kobo=30_000_000,
        approved_amount_kobo=30_000_000,
        interest_rate_bps=1200,
        tenure_months=12,
        monthly_instalment_kobo=2_800_000,
        bank_name="GTBank",
        requires_account_opening=True,
        bank_account_opened=False,
        bank_decision_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        title_released_at=None,
    )


class _StubLoans:
    def __init__(self, detail: LoanDetailRow | None) -> None:
        self._detail = detail

    async def get_detail(self, loan_id: UUID) -> LoanDetailRow | None:
        return self._detail


def _service(detail: LoanDetailRow | None) -> LoanQueryService:
    return LoanQueryService(loans=_StubLoans(detail))  # type: ignore[arg-type]


async def test_buyer_sees_own_loan() -> None:
    detail = _detail()
    result = await _service(detail).get_detail(detail.id, CurrentUser(user_id=_BUYER, role="buyer"))
    assert result is detail


async def test_admin_sees_any_loan() -> None:
    detail = _detail(buyer=uuid4())
    result = await _service(detail).get_detail(
        detail.id, CurrentUser(user_id=uuid4(), role="admin")
    )
    assert result is detail


async def test_unknown_loan_raises() -> None:
    with pytest.raises(LoanNotFound):
        await _service(None).get_detail(uuid4(), CurrentUser(user_id=_BUYER, role="buyer"))


async def test_stranger_forbidden() -> None:
    with pytest.raises(NotLoanViewer):
        await _service(_detail()).get_detail(uuid4(), CurrentUser(user_id=uuid4(), role="buyer"))
