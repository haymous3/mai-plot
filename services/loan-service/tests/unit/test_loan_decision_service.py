"""Unit tests for LoanDecisionWebhookService (SCRUM-76)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.loan_repo import LoanRow
from app.services.loan_decision import DecisionOutcome, LoanDecisionWebhookService

pytestmark = pytest.mark.asyncio

_SECRET = "test-bank-secret"


def _loan(*, status: str = "under_review", buyer: UUID | None = None) -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=buyer or uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
        status=status,
        bank_reference_id="BANK-REF-9",
        created_at=datetime.now(UTC),
    )


class _StubLoans:
    def __init__(self, *, loan: LoanRow | None, decision_updates: bool = True) -> None:
        self._loan = loan
        self._decision_updates = decision_updates
        self.recorded: list[dict[str, object]] = []

    async def get_by_bank_reference(self, bank_reference_id: str) -> LoanRow | None:
        return self._loan

    async def record_decision(self, loan_id: UUID, **kwargs: object) -> bool:
        self.recorded.append({"loan_id": loan_id, **kwargs})
        return self._decision_updates


class _StubNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def loan_decision(self, **kwargs: object) -> None:
        self.sent.append(kwargs)

    async def title_released(self, **kwargs: object) -> None:
        return None


def _service(loans: _StubLoans, notifier: _StubNotifier) -> LoanDecisionWebhookService:
    return LoanDecisionWebhookService(
        loans=loans,  # type: ignore[arg-type]
        notifier=notifier,
        secret=_SECRET,
    )


def _sign(body: dict[str, object]) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    sig = hmac.new(_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, sig


async def test_verify_signature_accepts_valid_and_rejects_invalid() -> None:
    svc = _service(_StubLoans(loan=None), _StubNotifier())
    raw, sig = _sign({"event": "loan.decision_ready"})
    assert svc.verify_signature(raw, sig) is True
    assert svc.verify_signature(raw, "deadbeef") is False
    assert svc.verify_signature(raw, None) is False


async def test_approved_records_terms_and_notifies() -> None:
    buyer = uuid4()
    loans = _StubLoans(loan=_loan(buyer=buyer))
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle(
        {
            "event": "loan.decision_ready",
            "data": {
                "reference": "BANK-REF-9",
                "decision": "approved",
                "approved_amount_kobo": 200_000_000,
                "interest_rate_bps": 2200,
                "tenure_months": 12,
                "monthly_instalment_kobo": 18_000_000,
            },
        }
    )
    assert outcome is DecisionOutcome.decided
    assert loans.recorded[0]["status"] == "approved"
    assert loans.recorded[0]["approved_amount_kobo"] == 200_000_000
    assert notifier.sent[0]["buyer_id"] == buyer
    assert notifier.sent[0]["decision"] == "approved"


async def test_rejected_records_null_terms() -> None:
    loans = _StubLoans(loan=_loan())
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle(
        {
            "event": "loan.decision_ready",
            "data": {"reference": "BANK-REF-9", "decision": "rejected"},
        }
    )
    assert outcome is DecisionOutcome.decided
    assert loans.recorded[0]["status"] == "rejected"
    assert loans.recorded[0]["approved_amount_kobo"] is None
    assert notifier.sent[0]["decision"] == "rejected"


async def test_already_decided_loan_is_duplicate() -> None:
    loans = _StubLoans(loan=_loan(status="approved"))
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle(
        {
            "event": "loan.decision_ready",
            "data": {"reference": "BANK-REF-9", "decision": "approved"},
        }
    )
    assert outcome is DecisionOutcome.duplicate
    assert loans.recorded == []  # no update attempted
    assert notifier.sent == []  # not re-notified


async def test_lost_update_race_is_duplicate_no_notify() -> None:
    loans = _StubLoans(loan=_loan(), decision_updates=False)  # guarded UPDATE matched 0 rows
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle(
        {
            "event": "loan.decision_ready",
            "data": {"reference": "BANK-REF-9", "decision": "approved"},
        }
    )
    assert outcome is DecisionOutcome.duplicate
    assert notifier.sent == []


async def test_unknown_reference_is_unknown_loan() -> None:
    loans = _StubLoans(loan=None)
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle(
        {"event": "loan.decision_ready", "data": {"reference": "NOPE", "decision": "approved"}}
    )
    assert outcome is DecisionOutcome.unknown_loan
    assert notifier.sent == []


async def test_wrong_event_is_ignored() -> None:
    loans = _StubLoans(loan=_loan())
    outcome = await _service(loans, _StubNotifier()).handle(
        {"event": "loan.something_else", "data": {"reference": "BANK-REF-9"}}
    )
    assert outcome is DecisionOutcome.ignored
    assert loans.recorded == []


async def test_invalid_decision_is_ignored() -> None:
    loans = _StubLoans(loan=_loan())
    outcome = await _service(loans, _StubNotifier()).handle(
        {"event": "loan.decision_ready", "data": {"reference": "BANK-REF-9", "decision": "maybe"}}
    )
    assert outcome is DecisionOutcome.ignored
    assert loans.recorded == []
