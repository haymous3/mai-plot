"""EscrowLedgerService — double-entry recording, balance, dual-approval gate."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.escrow_repo import EscrowBalance, PendingApproval
from app.services.escrow_ledger import (
    DUAL_APPROVAL_THRESHOLD_KOBO,
    EscrowLedgerService,
    InsufficientEscrowBalance,
    NoPendingApproval,
    SameApprover,
)

_TXN = uuid4()
_PE = uuid4()
_ADMIN_1 = uuid4()
_ADMIN_2 = uuid4()


class _StubLedgerRepo:
    """Faithful in-memory escrow ledger so the service's threshold/balance/
    approval logic is exercised for real."""

    def __init__(self) -> None:
        self.entries: dict[UUID, dict[str, object]] = {}

    async def record_entry(
        self,
        *,
        transaction_id: UUID,
        entry_type: str,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        requires_dual_approval: bool,
        approved_by_1: UUID | None,
    ) -> UUID:
        eid = uuid4()
        self.entries[eid] = {
            "id": eid,
            "transaction_id": transaction_id,
            "entry_type": entry_type,
            "amount_kobo": amount_kobo,
            "payment_event_id": payment_event_id,
            "requires_dual_approval": requires_dual_approval,
            "approved_by_1": approved_by_1,
            "approved_by_2": None,
        }
        return eid

    @staticmethod
    def _effective(e: dict[str, object]) -> bool:
        return not e["requires_dual_approval"] or e["approved_by_2"] is not None

    async def balance(self, transaction_id: UUID) -> EscrowBalance:
        bal = 0
        pending = 0
        for e in self.entries.values():
            if e["transaction_id"] != transaction_id:
                continue
            amt = int(e["amount_kobo"])  # type: ignore[call-overload]
            if e["entry_type"] == "credit":
                bal += amt
            elif self._effective(e):
                bal -= amt
            else:
                pending += amt
        return EscrowBalance(transaction_id=transaction_id, balance_kobo=bal, pending_kobo=pending)

    async def pending_approvals_for_payment_event(
        self, payment_event_id: UUID
    ) -> list[PendingApproval]:
        return [
            PendingApproval(
                entry_id=e["id"],  # type: ignore[arg-type]
                approved_by_1=e["approved_by_1"],  # type: ignore[arg-type]
                amount_kobo=int(e["amount_kobo"]),  # type: ignore[call-overload]
            )
            for e in self.entries.values()
            if e["payment_event_id"] == payment_event_id
            and e["requires_dual_approval"]
            and e["approved_by_2"] is None
        ]

    async def set_second_approval(self, entry_id: UUID, *, approver: UUID) -> bool:
        e = self.entries[entry_id]
        if e["approved_by_2"] is not None:
            return False
        e["approved_by_2"] = approver
        return True


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service() -> tuple[EscrowLedgerService, _StubLedgerRepo, _StubAudit]:
    repo = _StubLedgerRepo()
    audit = _StubAudit()
    svc = EscrowLedgerService(ledger=repo, audit=audit)  # type: ignore[arg-type]
    return svc, repo, audit


async def _credit(svc: EscrowLedgerService, amount: int) -> None:
    await svc.record_credit(
        transaction_id=_TXN, amount_kobo=amount, description="deposit", payment_event_id=_PE
    )


@pytest.mark.asyncio
async def test_credit_increases_balance() -> None:
    svc, _, audit = _service()
    await _credit(svc, 5_000_000_000)
    bal = await svc.balance(_TXN)
    assert bal.balance_kobo == 5_000_000_000
    assert bal.pending_kobo == 0
    assert audit.actions == ["escrow.credit"]


@pytest.mark.asyncio
async def test_small_debit_is_effective_immediately() -> None:
    svc, _, _ = _service()
    await _credit(svc, 5_000_000_000)
    # ₦5M debit — at/under the ₦10M threshold, no dual approval.
    await svc.record_debit(
        transaction_id=_TXN,
        amount_kobo=500_000_000,
        description="fee",
        payment_event_id=_PE,
        initiated_by=_ADMIN_1,
    )
    bal = await svc.balance(_TXN)
    assert bal.balance_kobo == 4_500_000_000  # debit took effect at once
    assert bal.pending_kobo == 0


@pytest.mark.asyncio
async def test_large_debit_is_pending_until_second_approval() -> None:
    svc, _, _ = _service()
    await _credit(svc, 5_000_000_000)
    # ₦20M debit — strictly above ₦10M → requires a second approval.
    assert 2_000_000_000 > DUAL_APPROVAL_THRESHOLD_KOBO
    await svc.record_debit(
        transaction_id=_TXN,
        amount_kobo=2_000_000_000,
        description="seller disbursement",
        payment_event_id=_PE,
        initiated_by=_ADMIN_1,
    )
    pending = await svc.balance(_TXN)
    assert pending.balance_kobo == 5_000_000_000  # not yet deducted
    assert pending.pending_kobo == 2_000_000_000

    approved = await svc.second_approval(payment_event_id=_PE, approver=_ADMIN_2)
    assert len(approved) == 1
    after = await svc.balance(_TXN)
    assert after.balance_kobo == 3_000_000_000  # now effective
    assert after.pending_kobo == 0


@pytest.mark.asyncio
async def test_debit_cannot_exceed_balance() -> None:
    svc, _, _ = _service()
    await _credit(svc, 1_000_000_000)
    with pytest.raises(InsufficientEscrowBalance):
        await svc.record_debit(
            transaction_id=_TXN,
            amount_kobo=1_000_000_001,
            description="too much",
            payment_event_id=_PE,
            initiated_by=_ADMIN_1,
        )


@pytest.mark.asyncio
async def test_second_approval_must_be_a_different_admin() -> None:
    svc, _, _ = _service()
    await _credit(svc, 5_000_000_000)
    await svc.record_debit(
        transaction_id=_TXN,
        amount_kobo=2_000_000_000,
        description="seller disbursement",
        payment_event_id=_PE,
        initiated_by=_ADMIN_1,
    )
    with pytest.raises(SameApprover):
        await svc.second_approval(payment_event_id=_PE, approver=_ADMIN_1)


@pytest.mark.asyncio
async def test_second_approval_with_nothing_pending_raises() -> None:
    svc, _, _ = _service()
    with pytest.raises(NoPendingApproval):
        await svc.second_approval(payment_event_id=_PE, approver=_ADMIN_2)
