"""Unit tests for LoanDecisionStageService (SCRUM-128)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.transaction_repo import TransactionStatus
from app.services.loan_stage import AdvanceOutcome, LoanDecisionStageService

pytestmark = pytest.mark.asyncio

_ACTOR = uuid4()


def _status(stage: str) -> TransactionStatus:
    return TransactionStatus(
        stage=stage,
        buyer_id=uuid4(),
        seller_id=uuid4(),
        listing_id=uuid4(),
        agreed_price_kobo=5_000_000_000,
        platform_fee_kobo=None,
    )


class _StubTransactions:
    def __init__(self, status: TransactionStatus | None) -> None:
        self._status = status
        self.stage_updates: list[str] = []
        self.events: list[tuple[str | None, str]] = []

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        return self._status

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        self.stage_updates.append(stage)

    async def append_event(
        self,
        *,
        transaction_id: UUID,
        event_type: str,
        to_stage: str,
        triggered_by: UUID | None,
        from_stage: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.events.append((from_stage, to_stage))


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(
    transactions: _StubTransactions, audit: _StubAudit | None = None
) -> LoanDecisionStageService:
    return LoanDecisionStageService(
        transactions=transactions,  # type: ignore[arg-type]
        audit=audit or _StubAudit(),  # type: ignore[arg-type]
        actor_id=_ACTOR,
    )


async def test_approved_advances_to_loan_approved() -> None:
    txns, audit = _StubTransactions(_status("loan_applied")), _StubAudit()
    result = await _service(txns, audit).advance(transaction_id=uuid4(), decision="approved")

    assert result.outcome == AdvanceOutcome.advanced
    assert result.stage == "loan_approved"
    assert txns.stage_updates == ["loan_approved"]
    assert txns.events == [("loan_applied", "loan_approved")]
    assert "transaction.stage_changed" in audit.actions


async def test_rejected_advances_to_loan_rejected() -> None:
    txns = _StubTransactions(_status("loan_applied"))
    result = await _service(txns).advance(transaction_id=uuid4(), decision="rejected")

    assert result.outcome == AdvanceOutcome.advanced
    assert txns.stage_updates == ["loan_rejected"]


async def test_already_decided_is_no_op() -> None:
    # A retried decision webhook on an already-advanced deal must not jump stages.
    txns = _StubTransactions(_status("loan_approved"))
    result = await _service(txns).advance(transaction_id=uuid4(), decision="approved")

    assert result.outcome == AdvanceOutcome.no_op
    assert txns.stage_updates == []
    assert result.stage == "loan_approved"


async def test_wrong_stage_is_no_op() -> None:
    # Not at loan_applied (e.g. a cash deal at payment_held) → no illegal jump.
    txns = _StubTransactions(_status("payment_held"))
    result = await _service(txns).advance(transaction_id=uuid4(), decision="approved")

    assert result.outcome == AdvanceOutcome.no_op
    assert txns.stage_updates == []


async def test_unknown_decision_ignored() -> None:
    txns = _StubTransactions(_status("loan_applied"))
    result = await _service(txns).advance(transaction_id=uuid4(), decision="maybe")

    assert result.outcome == AdvanceOutcome.ignored
    assert txns.stage_updates == []


async def test_unknown_transaction_ignored() -> None:
    txns = _StubTransactions(None)
    result = await _service(txns).advance(transaction_id=uuid4(), decision="approved")

    assert result.outcome == AdvanceOutcome.ignored
    assert txns.stage_updates == []
