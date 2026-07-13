"""Unit tests for CommissionDisbursementService (SCRUM-86)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.paystack import TransferResult
from app.repositories.escrow_repo import LedgerEntryRow
from app.services.disbursement import (
    CommissionDisbursementService,
    DisburseOutcome,
    DisburseRequest,
)
from app.services.escrow_ledger import InsufficientEscrowBalance

pytestmark = pytest.mark.asyncio

_THRESHOLD = 1_000_000_000  # ₦10M
_ACTOR = uuid4()


class _StubPayments:
    def __init__(self, *, pe_id: UUID, status: str = "initiated") -> None:
        self._row = type(
            "PE", (), {"id": pe_id, "status": status, "payment_type": "x", "amount_kobo": 0}
        )()
        self.updates: list[tuple[str, str | None]] = []

    async def upsert(self, **kwargs: object) -> object:
        return self._row

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        self.updates.append((status, provider_reference))


class _StubEscrow:
    def __init__(
        self, *, insufficient: bool = False, seed: list[LedgerEntryRow] | None = None
    ) -> None:
        self._insufficient = insufficient
        self.entries: list[LedgerEntryRow] = list(seed or [])
        self.debits: list[int] = []

    async def list_entries(self, transaction_id: UUID) -> list[LedgerEntryRow]:
        return self.entries

    async def record_debit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        initiated_by: UUID,
    ) -> UUID:
        if self._insufficient:
            raise InsufficientEscrowBalance()
        self.debits.append(amount_kobo)
        entry = _debit_entry(
            transaction_id=transaction_id,
            amount_kobo=amount_kobo,
            payment_event_id=payment_event_id,
        )
        self.entries.append(entry)
        return entry.id


class _StubReceipts:
    def __init__(self) -> None:
        self.written: list[UUID] = []

    async def write_receipt(self, payment_event_id: UUID, data: dict[str, object]) -> str:
        self.written.append(payment_event_id)
        return f"receipts/{payment_event_id}.json"

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, object]
    ) -> str:
        self.written.append(payment_event_id)
        return f"receipts/{payment_event_id}.pdf"


class _StubTransfer:
    def __init__(self, status: str = "success") -> None:
        self.calls = 0
        self._status = status

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_code: str
    ) -> TransferResult:
        self.calls += 1
        return TransferResult(reference=f"FAKE-{reference_hint}", status=self._status)  # type: ignore[arg-type]


class _StubAccount:
    def __init__(self, recipient_code: str) -> None:
        self.recipient_code = recipient_code


class _StubPayoutAccounts:
    """Returns a payout account (with recipient_code) for any user, or None to
    simulate a payee who hasn't registered one yet."""

    def __init__(self, *, recipient_code: str | None = "RCP_stub") -> None:
        self._recipient_code = recipient_code

    async def get(self, user_id: UUID) -> _StubAccount | None:
        if self._recipient_code is None:
            return None
        return _StubAccount(self._recipient_code)


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _debit_entry(
    *, transaction_id: UUID, amount_kobo: int, payment_event_id: UUID
) -> LedgerEntryRow:
    return LedgerEntryRow(
        id=uuid4(),
        transaction_id=transaction_id,
        entry_type="debit",
        amount_kobo=amount_kobo,
        description="c",
        payment_event_id=payment_event_id,
        requires_dual_approval=amount_kobo > _THRESHOLD,
        approved_by_1=_ACTOR,
        approved_by_2=None,
        approved_at=None,
        created_at=datetime.now(UTC),
    )


def _service(
    payments: _StubPayments,
    escrow: _StubEscrow,
    receipts: _StubReceipts,
    transfer: _StubTransfer,
    payout_accounts: _StubPayoutAccounts | None = None,
) -> CommissionDisbursementService:
    return CommissionDisbursementService(
        payments=payments,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        receipts=receipts,
        transfer_client=transfer,
        payout_accounts=payout_accounts or _StubPayoutAccounts(),  # type: ignore[arg-type]
        audit=_StubAudit(),  # type: ignore[arg-type]
        actor_id=_ACTOR,
    )


def _req(amount_kobo: int = 100_000_000) -> DisburseRequest:
    return DisburseRequest(
        commission_id=uuid4(),
        transaction_id=uuid4(),
        realtor_id=uuid4(),
        seller_id=uuid4(),
        amount_kobo=amount_kobo,
    )


async def test_happy_path_disburses() -> None:
    pe = uuid4()
    payments, escrow, receipts, transfer = (
        _StubPayments(pe_id=pe),
        _StubEscrow(),
        _StubReceipts(),
        _StubTransfer(),
    )
    result = await _service(payments, escrow, receipts, transfer).disburse(_req())

    assert result.outcome == DisburseOutcome.disbursed
    assert escrow.debits == [100_000_000]  # one debit recorded
    assert transfer.calls == 1
    assert ("completed", f"FAKE-{pe}") in payments.updates
    assert receipts.written == [pe]


async def test_already_completed_is_idempotent_noop() -> None:
    payments = _StubPayments(pe_id=uuid4(), status="completed")
    escrow, transfer = _StubEscrow(), _StubTransfer()
    result = await _service(payments, escrow, _StubReceipts(), transfer).disburse(_req())

    assert result.outcome == DisburseOutcome.already_disbursed
    assert escrow.debits == []  # no second debit
    assert transfer.calls == 0


async def test_insufficient_escrow_marks_failed() -> None:
    payments = _StubPayments(pe_id=uuid4())
    escrow, transfer = _StubEscrow(insufficient=True), _StubTransfer()
    result = await _service(payments, escrow, _StubReceipts(), transfer).disburse(_req())

    assert result.outcome == DisburseOutcome.insufficient_escrow
    assert ("failed", None) in payments.updates
    assert transfer.calls == 0  # no money moved


async def test_large_payout_pends_for_dual_approval() -> None:
    payments = _StubPayments(pe_id=uuid4())
    escrow, transfer = _StubEscrow(), _StubTransfer()
    # > ₦10M → the debit is recorded pending a second approval, not transferred.
    result = await _service(payments, escrow, _StubReceipts(), transfer).disburse(
        _req(amount_kobo=2_000_000_000)
    )

    assert result.outcome == DisburseOutcome.pending_approval
    assert ("processing", None) in payments.updates
    assert transfer.calls == 0


async def test_reentrant_completes_existing_effective_debit() -> None:
    # A prior run already recorded an effective debit for this payment_event;
    # a re-run must NOT double-debit, just complete the transfer.
    pe, tx = uuid4(), uuid4()
    existing = _debit_entry(transaction_id=tx, amount_kobo=100_000_000, payment_event_id=pe)
    payments = _StubPayments(pe_id=pe)
    escrow = _StubEscrow(seed=[existing])
    transfer = _StubTransfer()

    req = DisburseRequest(
        commission_id=uuid4(),
        transaction_id=tx,
        realtor_id=uuid4(),
        seller_id=uuid4(),
        amount_kobo=100_000_000,
    )
    result = await _service(payments, escrow, _StubReceipts(), transfer).disburse(req)

    assert result.outcome == DisburseOutcome.disbursed
    assert escrow.debits == []  # no NEW debit recorded
    assert transfer.calls == 1


async def test_no_payout_account_skips_debit() -> None:
    # The realtor hasn't registered a payout account -> resolve returns None
    # BEFORE any escrow debit; nothing is moved and a later sweep retries.
    payments = _StubPayments(pe_id=uuid4())
    escrow, transfer = _StubEscrow(), _StubTransfer()
    result = await _service(
        payments, escrow, _StubReceipts(), transfer, _StubPayoutAccounts(recipient_code=None)
    ).disburse(_req())

    assert result.outcome == DisburseOutcome.no_payout_account
    assert escrow.debits == []  # never debited
    assert transfer.calls == 0


async def test_pending_transfer_marks_processing() -> None:
    # A real async transfer returns 'pending' -> the payment_event is left open
    # (processing) for the transfer webhook to finalise; no receipt yet.
    pe = uuid4()
    payments = _StubPayments(pe_id=pe)
    escrow, receipts, transfer = _StubEscrow(), _StubReceipts(), _StubTransfer(status="pending")
    result = await _service(payments, escrow, receipts, transfer).disburse(_req())

    assert result.outcome == DisburseOutcome.processing
    assert escrow.debits == [100_000_000]  # money debited, transfer in flight
    assert transfer.calls == 1
    assert ("processing", f"FAKE-{pe}") in payments.updates
    assert receipts.written == []  # receipt written only on completion


async def test_transfer_failed_marks_failed() -> None:
    pe = uuid4()
    payments = _StubPayments(pe_id=pe)
    escrow, transfer = _StubEscrow(), _StubTransfer(status="failed")
    result = await _service(payments, escrow, _StubReceipts(), transfer).disburse(_req())

    assert result.outcome == DisburseOutcome.transfer_failed
    assert transfer.calls == 1
    assert ("failed", f"FAKE-{pe}") in payments.updates
