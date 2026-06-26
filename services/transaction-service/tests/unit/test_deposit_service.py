"""Unit tests for DepositService (SCRUM-83)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.paystack_charge import CheckoutInit
from app.repositories.payment_repo import PaymentEventRow
from app.repositories.transaction_repo import TransactionStatus
from app.security import CurrentUser
from app.services.deposit import (
    AlreadyDeposited,
    AmountMismatch,
    BuyerEmailMissing,
    DepositService,
    NotTransactionBuyer,
    TransactionNotFound,
)

pytestmark = pytest.mark.asyncio

_PRICE = 5_000_000_000


def _status(buyer_id: UUID) -> TransactionStatus:
    return TransactionStatus(
        stage="inspection_completed",
        buyer_id=buyer_id,
        seller_id=uuid4(),
        listing_id=uuid4(),
        agreed_price_kobo=_PRICE,
        platform_fee_kobo=None,
    )


class _StubTransactions:
    def __init__(
        self,
        status: TransactionStatus | None,
        *,
        email: str | None = "b@x.io",
        approved_loan_kobo: int | None = None,
    ) -> None:
        self._status = status
        self._email = email
        self._approved_loan_kobo = approved_loan_kobo

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        return self._status

    async def get_approved_loan_amount(self, transaction_id: UUID) -> int | None:
        return self._approved_loan_kobo

    async def get_user_email(self, user_id: UUID) -> str | None:
        return self._email


class _StubPayments:
    def __init__(self, *, status: str = "initiated") -> None:
        self.pe_id = uuid4()
        self._status = status
        self.updates: list[tuple[str, str | None]] = []

    async def upsert(self, **kwargs: object) -> PaymentEventRow:
        return PaymentEventRow(
            id=self.pe_id, status=self._status, payment_type="buyer_deposit", amount_kobo=_PRICE
        )

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        self.updates.append((status, provider_reference))


class _StubCharge:
    def __init__(self) -> None:
        self.calls = 0

    async def initialize(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str | None
    ) -> CheckoutInit:
        self.calls += 1
        return CheckoutInit(authorization_url=f"https://pay/{reference}", reference=reference)


def _service(
    transactions: _StubTransactions, payments: _StubPayments, charge: _StubCharge
) -> DepositService:
    return DepositService(
        transactions=transactions,  # type: ignore[arg-type]
        payments=payments,  # type: ignore[arg-type]
        charge_client=charge,
        callback_url="",
    )


def _buyer(buyer_id: UUID) -> CurrentUser:
    return CurrentUser(user_id=buyer_id, role="buyer")


async def test_happy_path_returns_checkout_url() -> None:
    buyer = uuid4()
    payments, charge = _StubPayments(), _StubCharge()
    result = await _service(_StubTransactions(_status(buyer)), payments, charge).initiate(
        transaction_id=uuid4(), buyer=_buyer(buyer), idempotency_key=uuid4(), amount_kobo=_PRICE
    )
    assert result.authorization_url == f"https://pay/{payments.pe_id}"
    assert result.payment_event_id == payments.pe_id
    assert charge.calls == 1


async def test_unknown_transaction() -> None:
    with pytest.raises(TransactionNotFound):
        await _service(_StubTransactions(None), _StubPayments(), _StubCharge()).initiate(
            transaction_id=uuid4(),
            buyer=_buyer(uuid4()),
            idempotency_key=uuid4(),
            amount_kobo=_PRICE,
        )


async def test_non_buyer_forbidden() -> None:
    with pytest.raises(NotTransactionBuyer):
        await _service(
            _StubTransactions(_status(uuid4())), _StubPayments(), _StubCharge()
        ).initiate(
            transaction_id=uuid4(),
            buyer=_buyer(uuid4()),
            idempotency_key=uuid4(),
            amount_kobo=_PRICE,
        )


async def test_amount_must_equal_agreed_price() -> None:
    buyer = uuid4()
    with pytest.raises(AmountMismatch):
        await _service(_StubTransactions(_status(buyer)), _StubPayments(), _StubCharge()).initiate(
            transaction_id=uuid4(),
            buyer=_buyer(buyer),
            idempotency_key=uuid4(),
            amount_kobo=_PRICE - 1,
        )


async def test_approved_loan_reduces_required_deposit() -> None:
    # price − approved loan is the buyer's contribution; the bank disburses the rest.
    buyer = uuid4()
    loan = 2_000_000_000
    payments, charge = _StubPayments(), _StubCharge()
    result = await _service(
        _StubTransactions(_status(buyer), approved_loan_kobo=loan), payments, charge
    ).initiate(
        transaction_id=uuid4(),
        buyer=_buyer(buyer),
        idempotency_key=uuid4(),
        amount_kobo=_PRICE - loan,
    )
    assert result.payment_event_id == payments.pe_id
    assert charge.calls == 1


async def test_full_price_rejected_when_loan_approved() -> None:
    # With a loan approved, paying the full price over-funds escrow → mismatch.
    buyer = uuid4()
    with pytest.raises(AmountMismatch):
        await _service(
            _StubTransactions(_status(buyer), approved_loan_kobo=2_000_000_000),
            _StubPayments(),
            _StubCharge(),
        ).initiate(
            transaction_id=uuid4(),
            buyer=_buyer(buyer),
            idempotency_key=uuid4(),
            amount_kobo=_PRICE,
        )


async def test_already_completed_conflicts() -> None:
    buyer = uuid4()
    charge = _StubCharge()
    with pytest.raises(AlreadyDeposited):
        await _service(
            _StubTransactions(_status(buyer)), _StubPayments(status="completed"), charge
        ).initiate(
            transaction_id=uuid4(), buyer=_buyer(buyer), idempotency_key=uuid4(), amount_kobo=_PRICE
        )
    assert charge.calls == 0  # no Paystack call once already paid


async def test_missing_email() -> None:
    buyer = uuid4()
    with pytest.raises(BuyerEmailMissing):
        await _service(
            _StubTransactions(_status(buyer), email=None), _StubPayments(), _StubCharge()
        ).initiate(
            transaction_id=uuid4(), buyer=_buyer(buyer), idempotency_key=uuid4(), amount_kobo=_PRICE
        )
