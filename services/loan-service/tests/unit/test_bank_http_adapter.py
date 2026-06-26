"""Unit tests for BankHttpAdapter (SCRUM-76) — driven by a stubbed httpx transport."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.adapters.bank import (
    AccountOpenResult,
    BankAdapterError,
    BankApplication,
    BankHttpAdapter,
    LoanStatusResult,
    LoanSubmission,
)

pytestmark = pytest.mark.asyncio


def _adapter(handler: httpx.MockTransport) -> BankHttpAdapter:
    return BankHttpAdapter(
        base_url="https://bank.example/api/",
        api_key="secret-key",
        timeout=5.0,
        retries=2,
        base_delay=0.0,  # no real backoff sleep in tests
        transport=handler,
    )


def _application() -> BankApplication:
    return BankApplication(
        loan_id=uuid4(),
        buyer_id=uuid4(),
        transaction_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
    )


async def test_submit_application_posts_and_parses() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"reference": "BANK-REF-9", "status": "received"})

    app_ = _application()
    result = await _adapter(httpx.MockTransport(handle)).submit_application(app_)

    assert result == LoanSubmission(bank_reference_id="BANK-REF-9", status="under_review")
    assert captured["method"] == "POST"
    assert captured["url"] == "https://bank.example/api/v1/loans"
    assert captured["auth"] == "Bearer secret-key"


async def test_get_status_parses_terms() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "approved",
                "approved_amount_kobo": 200_000_000,
                "interest_rate_bps": 2200,
                "tenure_months": 12,
                "monthly_instalment_kobo": 18_000_000,
            },
        )

    result = await _adapter(httpx.MockTransport(handle)).get_status("BANK-REF-9")
    assert result == LoanStatusResult(
        status="approved",
        approved_amount_kobo=200_000_000,
        interest_rate_bps=2200,
        tenure_months=12,
        monthly_instalment_kobo=18_000_000,
    )


async def test_open_account_parses_reference() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"account_reference": "ACCT-123"})

    result = await _adapter(httpx.MockTransport(handle)).open_account(uuid4())
    assert result == AccountOpenResult(account_reference="ACCT-123")


async def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)  # transient — raise_for_status fails, retried
        return httpx.Response(200, json={"reference": "BANK-REF-1", "status": "under_review"})

    result = await _adapter(httpx.MockTransport(handle)).submit_application(_application())
    assert result.bank_reference_id == "BANK-REF-1"
    assert calls["n"] == 2  # first attempt failed, second succeeded


async def test_exhausted_retries_raises_bank_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(BankAdapterError):
        await _adapter(httpx.MockTransport(handle)).submit_application(_application())
