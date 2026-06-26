"""Unit tests for the bank adapter layer (SCRUM-75)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.adapters.bank import (
    BankAdapterError,
    BankApplication,
    FakeBankAdapter,
    build_bank_adapter_registry,
    call_with_resilience,
)

pytestmark = pytest.mark.asyncio


async def test_resilience_retries_then_succeeds() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await call_with_resilience(flaky, op_name="submit", retries=3, base_delay=0, timeout=1)
    assert result == "ok"
    assert calls["n"] == 3


async def test_resilience_raises_after_exhausting_retries() -> None:
    calls = {"n": 0}

    async def always_fail() -> str:
        calls["n"] += 1
        raise RuntimeError("down")

    with pytest.raises(BankAdapterError):
        await call_with_resilience(
            always_fail, op_name="submit", retries=3, base_delay=0, timeout=1
        )
    assert calls["n"] == 4  # initial + 3 retries


async def test_resilience_times_out_each_attempt() -> None:
    calls = {"n": 0}

    async def slow() -> str:
        calls["n"] += 1
        await asyncio.sleep(1)
        return "never"

    with pytest.raises(BankAdapterError):
        await call_with_resilience(slow, op_name="status", retries=2, base_delay=0, timeout=0.01)
    assert calls["n"] == 3  # each attempt timed out + was retried


async def test_fake_adapter_accepts_into_review() -> None:
    adapter = FakeBankAdapter()
    loan_id = uuid4()
    submission = await adapter.submit_application(
        BankApplication(
            loan_id=loan_id,
            buyer_id=uuid4(),
            transaction_id=uuid4(),
            requested_amount_kobo=1_000_000,
            tenure_months=12,
        )
    )
    assert submission.status == "under_review"
    assert submission.bank_reference_id == f"FAKE-BANK-{loan_id}"
    assert (await adapter.get_status(submission.bank_reference_id)).status == "under_review"


async def test_registry_returns_fake_when_disabled_and_memoises() -> None:
    registry = build_bank_adapter_registry(enabled=False, timeout=30, retries=3, base_delay=0.5)
    a = registry.for_partner(short_code="BANK001")
    b = registry.for_partner(short_code="BANK001")
    assert isinstance(a, FakeBankAdapter)
    assert a is b  # memoised per short_code
