"""Unit tests for BankWebhookDispatcher (SCRUM-77) — event routing + HMAC."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import pytest

from app.services.bank_webhook import BankWebhookDispatcher
from app.services.loan_decision import DecisionOutcome
from app.services.loan_repayment import RepaymentOutcome

pytestmark = pytest.mark.asyncio

_SECRET = "dispatch-secret"


class _StubDecision:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle(self, payload: dict[str, Any]) -> DecisionOutcome:
        self.calls.append(payload)
        return DecisionOutcome.decided


class _StubRepayment:
    def __init__(self) -> None:
        self.milestones: list[dict[str, Any]] = []
        self.repaids: list[dict[str, Any]] = []

    async def handle_milestone(self, payload: dict[str, Any]) -> RepaymentOutcome:
        self.milestones.append(payload)
        return RepaymentOutcome.recorded

    async def handle_fully_repaid(self, payload: dict[str, Any]) -> RepaymentOutcome:
        self.repaids.append(payload)
        return RepaymentOutcome.released


def _dispatcher() -> tuple[BankWebhookDispatcher, _StubDecision, _StubRepayment]:
    decision = _StubDecision()
    repayment = _StubRepayment()
    dispatcher = BankWebhookDispatcher(
        secret=_SECRET,
        decision=decision,  # type: ignore[arg-type]
        repayment=repayment,  # type: ignore[arg-type]
    )
    return dispatcher, decision, repayment


async def test_verify_signature() -> None:
    dispatcher, _, _ = _dispatcher()
    raw = b'{"event":"x"}'
    sig = hmac.new(_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert dispatcher.verify_signature(raw, sig) is True
    assert dispatcher.verify_signature(raw, "bad") is False
    assert dispatcher.verify_signature(raw, None) is False


async def test_routes_decision_event() -> None:
    dispatcher, decision, repayment = _dispatcher()
    out = await dispatcher.handle({"event": "loan.decision_ready", "data": {}})
    assert out == "decided"
    assert len(decision.calls) == 1
    assert repayment.milestones == [] and repayment.repaids == []


async def test_routes_milestone_event() -> None:
    dispatcher, decision, repayment = _dispatcher()
    out = await dispatcher.handle({"event": "repayment.milestone", "data": {}})
    assert out == "recorded"
    assert len(repayment.milestones) == 1
    assert decision.calls == []


async def test_routes_fully_repaid_event() -> None:
    dispatcher, _, repayment = _dispatcher()
    out = await dispatcher.handle({"event": "loan.fully_repaid", "data": {}})
    assert out == "released"
    assert len(repayment.repaids) == 1


async def test_unknown_event_ignored() -> None:
    dispatcher, decision, repayment = _dispatcher()
    out = await dispatcher.handle({"event": "loan.something", "data": {}})
    assert out == "ignored"
    assert decision.calls == [] and repayment.milestones == [] and repayment.repaids == []
