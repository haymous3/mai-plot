"""Unit tests for LoanRepaymentWebhookService (SCRUM-77)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.loan_repo import LoanRow
from app.services.loan_repayment import LoanRepaymentWebhookService, RepaymentOutcome

pytestmark = pytest.mark.asyncio


def _loan(*, buyer: UUID | None = None) -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=buyer or uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
        status="repaying",
        bank_reference_id="BANK-REF-9",
        created_at=datetime.now(UTC),
    )


class _StubLoans:
    def __init__(self, *, loan: LoanRow | None, fully_repaid_ok: bool = True) -> None:
        self._loan = loan
        self._fully_repaid_ok = fully_repaid_ok
        self.repaid_calls: list[UUID] = []

    async def get_by_bank_reference(self, bank_reference_id: str) -> LoanRow | None:
        return self._loan

    async def mark_fully_repaid(self, loan_id: UUID) -> bool:
        self.repaid_calls.append(loan_id)
        return self._fully_repaid_ok


class _StubMilestones:
    def __init__(self, *, inserted: bool = True) -> None:
        self._inserted = inserted
        self.upserts: list[dict[str, object]] = []

    async def upsert_milestone(self, loan_id: UUID, **kwargs: object) -> bool:
        self.upserts.append({"loan_id": loan_id, **kwargs})
        return self._inserted


class _StubNotifier:
    def __init__(self) -> None:
        self.title_released_calls: list[dict[str, object]] = []

    async def loan_decision(self, **kwargs: object) -> None:
        return None

    async def title_released(self, **kwargs: object) -> None:
        self.title_released_calls.append(kwargs)

    async def account_opened(self, **kwargs: object) -> None:
        return None

    async def disbursed(self, **kwargs: object) -> None:
        return None


def _service(
    loans: _StubLoans, milestones: _StubMilestones, notifier: _StubNotifier
) -> LoanRepaymentWebhookService:
    return LoanRepaymentWebhookService(
        loans=loans,  # type: ignore[arg-type]
        milestones=milestones,  # type: ignore[arg-type]
        notifier=notifier,
    )


def _milestone_payload(**data: object) -> dict[str, object]:
    base: dict[str, object] = {
        "reference": "BANK-REF-9",
        "due_date": "2026-07-01",
        "amount_due_kobo": 23_000_000,
        "amount_paid_kobo": 23_000_000,
        "status": "paid",
        "milestone_reference": "MS-001",
    }
    base.update(data)
    return {"event": "repayment.milestone", "data": base}


async def test_milestone_recorded_when_inserted() -> None:
    loans = _StubLoans(loan=_loan())
    milestones = _StubMilestones(inserted=True)
    outcome = await _service(loans, milestones, _StubNotifier()).handle_milestone(
        _milestone_payload()
    )
    assert outcome is RepaymentOutcome.recorded
    up = milestones.upserts[0]
    assert up["due_date"] == date(2026, 7, 1)
    assert up["status"] == "paid"
    assert up["amount_paid_kobo"] == 23_000_000
    assert up["bank_reference"] == "MS-001"


async def test_milestone_updated_when_conflict() -> None:
    milestones = _StubMilestones(inserted=False)
    svc = _service(_StubLoans(loan=_loan()), milestones, _StubNotifier())
    outcome = await svc.handle_milestone(_milestone_payload())
    assert outcome is RepaymentOutcome.updated


async def test_milestone_invalid_status_defaults_to_pending() -> None:
    milestones = _StubMilestones()
    await _service(_StubLoans(loan=_loan()), milestones, _StubNotifier()).handle_milestone(
        _milestone_payload(status="weird")
    )
    assert milestones.upserts[0]["status"] == "pending"
    assert milestones.upserts[0]["paid_at"] is None  # only set when status == paid


async def test_milestone_unknown_loan() -> None:
    milestones = _StubMilestones()
    outcome = await _service(_StubLoans(loan=None), milestones, _StubNotifier()).handle_milestone(
        _milestone_payload()
    )
    assert outcome is RepaymentOutcome.unknown_loan
    assert milestones.upserts == []


async def test_milestone_missing_due_date_is_ignored() -> None:
    milestones = _StubMilestones()
    svc = _service(_StubLoans(loan=_loan()), milestones, _StubNotifier())
    outcome = await svc.handle_milestone(
        {"event": "repayment.milestone", "data": {"reference": "BANK-REF-9"}}
    )
    assert outcome is RepaymentOutcome.ignored
    assert milestones.upserts == []


async def test_fully_repaid_releases_title_and_notifies() -> None:
    buyer = uuid4()
    loans = _StubLoans(loan=_loan(buyer=buyer), fully_repaid_ok=True)
    notifier = _StubNotifier()
    outcome = await _service(loans, _StubMilestones(), notifier).handle_fully_repaid(
        {"event": "loan.fully_repaid", "data": {"reference": "BANK-REF-9"}}
    )
    assert outcome is RepaymentOutcome.released
    assert notifier.title_released_calls[0]["buyer_id"] == buyer


async def test_fully_repaid_duplicate_does_not_notify() -> None:
    loans = _StubLoans(loan=_loan(), fully_repaid_ok=False)  # title already released
    notifier = _StubNotifier()
    outcome = await _service(loans, _StubMilestones(), notifier).handle_fully_repaid(
        {"event": "loan.fully_repaid", "data": {"reference": "BANK-REF-9"}}
    )
    assert outcome is RepaymentOutcome.duplicate
    assert notifier.title_released_calls == []


async def test_fully_repaid_unknown_loan() -> None:
    svc = _service(_StubLoans(loan=None), _StubMilestones(), _StubNotifier())
    outcome = await svc.handle_fully_repaid(
        {"event": "loan.fully_repaid", "data": {"reference": "GHOST"}}
    )
    assert outcome is RepaymentOutcome.unknown_loan
