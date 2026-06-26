"""Unit tests for SellerDisbursementService (SCRUM-85)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.paystack import TransferResult
from app.adapters.receipt_storage import render_receipt_pdf
from app.repositories.escrow_repo import LedgerEntryRow
from app.repositories.payment_repo import PaymentEventRow
from app.repositories.transaction_repo import CommissionGate, SettleableDeal
from app.services.escrow_ledger import InsufficientEscrowBalance
from app.services.seller_disbursement import SellerDisbursementService

pytestmark = pytest.mark.asyncio

_THRESHOLD = 1_000_000_000  # ₦10M dual-approval threshold
_PRICE = 800_000_000  # ₦8M — keeps seller net under the threshold
_FEE = 20_000_000  # 2.5%
_COMMISSION = 16_000_000  # 2%
_ACTOR = uuid4()


def _deal() -> SettleableDeal:
    return SettleableDeal(
        transaction_id=uuid4(),
        buyer_id=uuid4(),
        seller_id=uuid4(),
        agreed_price_kobo=_PRICE,
        platform_fee_kobo=_FEE,
    )


class _StubTransactions:
    def __init__(self, deal: SettleableDeal, gate: CommissionGate) -> None:
        self._deal = deal
        self._gate = gate

    async def list_settleable(self, *, hold_hours: int, limit: int = 500) -> list[SettleableDeal]:
        return [self._deal]

    async def commission_gate(self, transaction_id: UUID) -> CommissionGate:
        return self._gate


class _StubPayments:
    def __init__(self, *, status_by_type: dict[str, str] | None = None) -> None:
        self._status = status_by_type or {}
        self.updates: list[str] = []

    async def upsert(self, **kwargs: object) -> PaymentEventRow:
        ptype = str(kwargs["payment_type"])
        return PaymentEventRow(
            id=uuid4(),
            status=self._status.get(ptype, "initiated"),
            payment_type=ptype,
            amount_kobo=int(kwargs["amount_kobo"]),  # type: ignore[call-overload]
        )

    async def update_status(
        self, payment_event_id: UUID, status: str, *, provider_reference: str | None = None
    ) -> None:
        self.updates.append(status)


class _StubEscrow:
    def __init__(self, *, insufficient: bool = False) -> None:
        self._insufficient = insufficient
        self.entries: list[LedgerEntryRow] = []
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
        entry = LedgerEntryRow(
            id=uuid4(),
            transaction_id=transaction_id,
            entry_type="debit",
            amount_kobo=amount_kobo,
            description="d",
            payment_event_id=payment_event_id,
            requires_dual_approval=amount_kobo > _THRESHOLD,
            approved_by_1=_ACTOR,
            approved_by_2=None,
            approved_at=None,
            created_at=datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry.id


class _StubReceipts:
    def __init__(self) -> None:
        self.pdfs: list[UUID] = []

    async def write_receipt(self, payment_event_id: UUID, data: dict[str, object]) -> str:
        return "x"

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, object]
    ) -> str:
        self.pdfs.append(payment_event_id)
        return f"receipts/{payment_event_id}.pdf"


class _StubTransfer:
    def __init__(self) -> None:
        self.calls = 0

    async def transfer(
        self, *, reference_hint: str, amount_kobo: int, recipient_id: UUID
    ) -> TransferResult:
        self.calls += 1
        return TransferResult(reference=f"FAKE-{reference_hint}", status="success")


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(
    transactions: _StubTransactions,
    payments: _StubPayments,
    escrow: _StubEscrow,
    receipts: _StubReceipts,
    transfer: _StubTransfer,
) -> SellerDisbursementService:
    return SellerDisbursementService(
        transactions=transactions,  # type: ignore[arg-type]
        payments=payments,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        receipts=receipts,
        transfer_client=transfer,
        audit=_StubAudit(),  # type: ignore[arg-type]
        actor_id=_ACTOR,
        hold_hours=48,
    )


async def test_happy_path_settles_fee_and_seller() -> None:
    deal = _deal()
    escrow, transfer, receipts = _StubEscrow(), _StubTransfer(), _StubReceipts()
    payments = _StubPayments()
    gate = CommissionGate(amount_kobo=_COMMISSION, has_completed_inspection=True)
    result = await _service(
        _StubTransactions(deal, gate), payments, escrow, receipts, transfer
    ).run()

    assert result.disbursed == 1
    # platform fee debit + seller net debit, in that order
    assert escrow.debits == [_FEE, _PRICE - _FEE - _COMMISSION]
    assert transfer.calls == 1
    assert len(receipts.pdfs) == 1


async def test_no_realtor_treats_commission_as_zero() -> None:
    deal = _deal()
    escrow, transfer = _StubEscrow(), _StubTransfer()
    gate = CommissionGate(amount_kobo=None, has_completed_inspection=False)
    result = await _service(
        _StubTransactions(deal, gate), _StubPayments(), escrow, _StubReceipts(), transfer
    ).run()

    assert result.disbursed == 1
    assert escrow.debits == [_FEE, _PRICE - _FEE]  # no commission reserved


async def test_commission_not_accrued_waits() -> None:
    deal = _deal()
    escrow, transfer = _StubEscrow(), _StubTransfer()
    gate = CommissionGate(amount_kobo=None, has_completed_inspection=True)
    result = await _service(
        _StubTransactions(deal, gate), _StubPayments(), escrow, _StubReceipts(), transfer
    ).run()

    assert result.waiting == 1
    assert escrow.debits == []  # nothing moved
    assert transfer.calls == 0


async def test_insufficient_escrow_waits() -> None:
    deal = _deal()
    transfer = _StubTransfer()
    gate = CommissionGate(amount_kobo=_COMMISSION, has_completed_inspection=True)
    result = await _service(
        _StubTransactions(deal, gate),
        _StubPayments(),
        _StubEscrow(insufficient=True),
        _StubReceipts(),
        transfer,
    ).run()

    assert result.waiting == 1
    assert transfer.calls == 0  # no money moved


async def test_large_seller_net_pends_for_dual_approval() -> None:
    # A big deal where the seller net exceeds ₦10M -> the seller debit pends.
    deal = SettleableDeal(
        transaction_id=uuid4(),
        buyer_id=uuid4(),
        seller_id=uuid4(),
        agreed_price_kobo=20_000_000_000,
        platform_fee_kobo=100_000_000,
    )
    escrow, transfer = _StubEscrow(), _StubTransfer()
    gate = CommissionGate(amount_kobo=0, has_completed_inspection=False)
    result = await _service(
        _StubTransactions(deal, gate), _StubPayments(), escrow, _StubReceipts(), transfer
    ).run()

    assert result.pending == 1
    assert transfer.calls == 0  # not transferred until approved


async def test_seller_already_disbursed_is_idempotent() -> None:
    deal = _deal()
    transfer = _StubTransfer()
    payments = _StubPayments(status_by_type={"seller_disbursement": "completed"})
    gate = CommissionGate(amount_kobo=_COMMISSION, has_completed_inspection=True)
    result = await _service(
        _StubTransactions(deal, gate), payments, _StubEscrow(), _StubReceipts(), transfer
    ).run()

    # platform fee settles, seller already done -> no transfer this run.
    assert result.disbursed == 0
    assert transfer.calls == 0


async def test_render_receipt_pdf_produces_pdf_bytes() -> None:
    # async only to satisfy the module asyncio mark — no await needed.
    pdf = render_receipt_pdf("Seller disbursement receipt", {"Net to seller (kobo)": 123})
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 200
