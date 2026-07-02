"""Unit tests for LoanApplicationService (SCRUM-75)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.bank import build_bank_adapter_registry
from app.repositories.bank_partner_repo import BankPartner
from app.repositories.loan_repo import LoanRow
from app.repositories.transaction_repo import TransactionInfo
from app.security import CurrentUser
from app.services.loan_application import (
    BankPartnerUnavailable,
    DailyLimitReached,
    LoanApplicationResult,
    LoanApplicationService,
    LoanBandViolation,
    LoanCapExceeded,
    NotTransactionBuyer,
    TenureViolation,
    TransactionNotFound,
)

pytestmark = pytest.mark.asyncio

_PRICE = 800_000_000  # cap = ₦4M (400_000_000 kobo)
_AMOUNT = 300_000_000


def _info(buyer_id: UUID) -> TransactionInfo:
    return TransactionInfo(
        buyer_id=buyer_id, agreed_price_kobo=_PRICE, stage="inspection_completed"
    )


def _partner() -> BankPartner:
    return BankPartner(
        id=uuid4(),
        short_code="BANK001",
        loan_min_kobo=1_000_000,
        loan_max_kobo=500_000_000,
        interest_rate_bps=2200,
        min_tenure_months=6,
        max_tenure_months=36,
        requires_account_opening=True,
    )


def _loan_row(buyer: UUID) -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=buyer,
        bank_partner_id=uuid4(),
        requested_amount_kobo=_AMOUNT,
        tenure_months=12,
        status="under_review",
        bank_reference_id="FAKE-BANK-x",
        created_at=datetime.now(UTC),
    )


class _StubTransactions:
    def __init__(self, info: TransactionInfo | None) -> None:
        self._info = info

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        return self._info


class _StubPartners:
    def __init__(self, partner: BankPartner | None) -> None:
        self._partner = partner

    async def get_active(self, partner_id: UUID) -> BankPartner | None:
        return self._partner


class _StubLoans:
    def __init__(self, *, existing: LoanRow | None = None, count_today: int = 0) -> None:
        self._existing = existing
        self._count = count_today
        self.created: list[dict[str, object]] = []
        self.refs: list[tuple[str, str]] = []
        self.loan_id = uuid4()

    async def get_by_idempotency(self, buyer_id: UUID, idempotency_key: UUID) -> LoanRow | None:
        return self._existing

    async def count_today(self, buyer_id: UUID) -> int:
        return self._count

    async def create(self, **kwargs: object) -> tuple[UUID, bool]:
        self.created.append(kwargs)
        return self.loan_id, True

    async def set_bank_reference(
        self, loan_id: UUID, *, bank_reference_id: str, status: str
    ) -> None:
        self.refs.append((status, bank_reference_id))

    async def get(self, loan_id: UUID) -> LoanRow | None:
        return None


def _service(
    transactions: _StubTransactions, partners: _StubPartners, loans: _StubLoans
) -> LoanApplicationService:
    return LoanApplicationService(
        transactions=transactions,  # type: ignore[arg-type]
        partners=partners,  # type: ignore[arg-type]
        loans=loans,  # type: ignore[arg-type]
        registry=build_bank_adapter_registry(enabled=False, timeout=30, retries=3, base_delay=0),
        loan_cap_bps=5000,
        max_applications_per_day=3,
    )


def _buyer(buyer_id: UUID) -> CurrentUser:
    return CurrentUser(user_id=buyer_id, role="buyer")


async def _apply(
    svc: LoanApplicationService, buyer: UUID, *, amount: int = _AMOUNT, tenure: int = 12
) -> LoanApplicationResult:
    return await svc.apply(
        buyer=_buyer(buyer),
        transaction_id=uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=amount,
        tenure_months=tenure,
        idempotency_key=uuid4(),
    )


async def test_happy_path_submits_to_bank() -> None:
    buyer = uuid4()
    loans = _StubLoans()
    result = await _apply(
        _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), loans), buyer
    )
    assert result.status == "under_review"
    assert result.bank_reference_id == f"FAKE-BANK-{loans.loan_id}"
    assert loans.refs == [("under_review", f"FAKE-BANK-{loans.loan_id}")]


async def test_applicant_fields_passed_to_create() -> None:
    buyer = uuid4()
    loans = _StubLoans()
    svc = _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), loans)
    await svc.apply(
        buyer=_buyer(buyer),
        transaction_id=uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=_AMOUNT,
        tenure_months=12,
        idempotency_key=uuid4(),
        employment_status="employed",
        monthly_income_kobo=90_000_000,
    )
    assert loans.created[0]["employment_status"] == "employed"
    assert loans.created[0]["monthly_income_kobo"] == 90_000_000


async def test_unknown_transaction() -> None:
    with pytest.raises(TransactionNotFound):
        await _apply(
            _service(_StubTransactions(None), _StubPartners(_partner()), _StubLoans()), uuid4()
        )


async def test_non_buyer_forbidden() -> None:
    with pytest.raises(NotTransactionBuyer):
        await _apply(
            _service(_StubTransactions(_info(uuid4())), _StubPartners(_partner()), _StubLoans()),
            uuid4(),
        )


async def test_loan_cap_exceeded() -> None:
    buyer = uuid4()
    with pytest.raises(LoanCapExceeded):
        # > 50% of ₦8M = > ₦4M
        await _apply(
            _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), _StubLoans()),
            buyer,
            amount=_PRICE // 2 + 1,
        )


async def test_inactive_partner() -> None:
    buyer = uuid4()
    with pytest.raises(BankPartnerUnavailable):
        await _apply(
            _service(_StubTransactions(_info(buyer)), _StubPartners(None), _StubLoans()), buyer
        )


async def test_amount_below_partner_band() -> None:
    buyer = uuid4()
    with pytest.raises(LoanBandViolation):
        await _apply(
            _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), _StubLoans()),
            buyer,
            amount=500_000,  # below loan_min_kobo 1_000_000
        )


async def test_tenure_out_of_range() -> None:
    buyer = uuid4()
    with pytest.raises(TenureViolation):
        await _apply(
            _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), _StubLoans()),
            buyer,
            tenure=60,  # > max_tenure_months 36
        )


async def test_daily_limit_reached() -> None:
    buyer = uuid4()
    with pytest.raises(DailyLimitReached):
        await _apply(
            _service(
                _StubTransactions(_info(buyer)),
                _StubPartners(_partner()),
                _StubLoans(count_today=3),
            ),
            buyer,
        )


async def test_idempotent_retry_returns_existing() -> None:
    buyer = uuid4()
    existing = _loan_row(buyer)
    loans = _StubLoans(existing=existing)
    result = await _apply(
        _service(_StubTransactions(_info(buyer)), _StubPartners(_partner()), loans), buyer
    )
    assert result.loan_id == existing.id
    assert loans.created == []  # no new row, no bank submission
    assert loans.refs == []
