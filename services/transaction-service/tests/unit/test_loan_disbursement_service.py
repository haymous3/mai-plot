"""Unit tests for LoanDisbursementCreditService (SCRUM-128)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.escrow_repo import LedgerEntryRow
from app.services.loan_disbursement import (
    CreditOutcome,
    CreditRequest,
    LoanDisbursementCreditService,
)

pytestmark = pytest.mark.asyncio

_ACTOR = uuid4()


class _StubPayments:
    def __init__(self, *, pe_id: UUID, status: str = "initiated") -> None:
        self._row = type(
            "PE",
            (),
            {"id": pe_id, "status": status, "payment_type": "loan_disbursement", "amount_kobo": 0},
        )()
        self.updates: list[tuple[str, str | None]] = []

    async def upsert(self, **kwargs: object) -> object:
        return self._row

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        self.updates.append((status, provider_reference))


class _StubEscrow:
    def __init__(self, *, seed: list[LedgerEntryRow] | None = None) -> None:
        self.entries: list[LedgerEntryRow] = list(seed or [])
        self.credits: list[int] = []

    async def list_entries(self, transaction_id: UUID) -> list[LedgerEntryRow]:
        return self.entries

    async def record_credit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        recorded_by: UUID | None = None,
    ) -> UUID:
        self.credits.append(amount_kobo)
        entry = _credit_entry(
            transaction_id=transaction_id,
            amount_kobo=amount_kobo,
            payment_event_id=payment_event_id,
        )
        self.entries.append(entry)
        return entry.id


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _credit_entry(
    *, transaction_id: UUID, amount_kobo: int, payment_event_id: UUID
) -> LedgerEntryRow:
    return LedgerEntryRow(
        id=uuid4(),
        transaction_id=transaction_id,
        entry_type="credit",
        amount_kobo=amount_kobo,
        description="loan",
        payment_event_id=payment_event_id,
        requires_dual_approval=False,
        approved_by_1=_ACTOR,
        approved_by_2=None,
        approved_at=None,
        created_at=datetime.now(UTC),
    )


def _service(
    payments: _StubPayments, escrow: _StubEscrow, audit: _StubAudit | None = None
) -> LoanDisbursementCreditService:
    return LoanDisbursementCreditService(
        payments=payments,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        audit=audit or _StubAudit(),  # type: ignore[arg-type]
        actor_id=_ACTOR,
    )


def _req(amount_kobo: int = 2_000_000_000) -> CreditRequest:
    return CreditRequest(
        loan_id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=uuid4(),
        amount_kobo=amount_kobo,
    )


async def test_happy_path_credits_escrow() -> None:
    pe = uuid4()
    payments, escrow, audit = _StubPayments(pe_id=pe), _StubEscrow(), _StubAudit()
    result = await _service(payments, escrow, audit).credit(_req(2_000_000_000))

    assert result.outcome == CreditOutcome.credited
    assert escrow.credits == [2_000_000_000]
    assert ("completed", None) in payments.updates
    assert "loan.disbursement_credited" in audit.actions


async def test_already_completed_is_idempotent_noop() -> None:
    payments = _StubPayments(pe_id=uuid4(), status="completed")
    escrow = _StubEscrow()
    result = await _service(payments, escrow).credit(_req())

    assert result.outcome == CreditOutcome.already_credited
    assert escrow.credits == []  # no second credit


async def test_reentrant_does_not_double_credit() -> None:
    # A prior run already credited this payment_event but crashed before the
    # status flip; a re-run must NOT credit again, just complete.
    pe, tx = uuid4(), uuid4()
    existing = _credit_entry(transaction_id=tx, amount_kobo=2_000_000_000, payment_event_id=pe)
    payments = _StubPayments(pe_id=pe)
    escrow = _StubEscrow(seed=[existing])

    req = CreditRequest(
        loan_id=uuid4(), transaction_id=tx, buyer_id=uuid4(), amount_kobo=2_000_000_000
    )
    result = await _service(payments, escrow).credit(req)

    assert result.outcome == CreditOutcome.credited
    assert escrow.credits == []  # no NEW credit
    assert ("completed", None) in payments.updates


async def test_idempotency_key_is_deterministic_per_loan() -> None:
    loan = uuid4()
    k1 = LoanDisbursementCreditService._idempotency_key(loan)
    k2 = LoanDisbursementCreditService._idempotency_key(loan)
    assert k1 == k2
    assert k1 != LoanDisbursementCreditService._idempotency_key(uuid4())
