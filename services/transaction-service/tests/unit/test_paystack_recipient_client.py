"""Unit tests for the real PaystackHttpRecipientClient (SCRUM-145).

Exercises the transfer-recipient client against an httpx.MockTransport so no
network is touched. Covers the happy path plus every failure mode mapping to
PaystackRecipientError, and asserts the secret + account number never leak into
an error string.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.paystack_recipient import (
    PaystackHttpRecipientClient,
    PaystackRecipientError,
    RecipientResult,
)

pytestmark = pytest.mark.asyncio

_SECRET = "sk_test_deadbeef"  # noqa: S105 - throwaway fake key for tests
_ACCOUNT = "0123456789"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> PaystackHttpRecipientClient:
    return PaystackHttpRecipientClient(
        secret_key=_SECRET,
        base_url="https://api.paystack.co",
        transport=httpx.MockTransport(handler),
    )


async def test_create_recipient_returns_code() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"status": True, "data": {"recipient_code": "RCP_abc123"}},
        )

    result = await _client(handler).create_recipient(
        account_number=_ACCOUNT, bank_code="058", account_name="Ada A"
    )

    assert result == RecipientResult(recipient_code="RCP_abc123")
    assert captured["url"] == "https://api.paystack.co/transferrecipient"
    assert captured["auth"] == f"Bearer {_SECRET}"
    assert captured["body"] == {
        "type": "nuban",
        "name": "Ada A",
        "account_number": _ACCOUNT,
        "bank_code": "058",
        "currency": "NGN",
    }


async def test_provider_status_false_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "message": "Unknown bank code"})

    with pytest.raises(PaystackRecipientError) as exc:
        await _client(handler).create_recipient(
            account_number=_ACCOUNT, bank_code="000", account_name="Ada A"
        )
    assert "Unknown bank code" in str(exc.value)


async def test_success_body_missing_recipient_code_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": True, "data": {}})

    with pytest.raises(PaystackRecipientError):
        await _client(handler).create_recipient(
            account_number=_ACCOUNT, bank_code="058", account_name="Ada A"
        )


async def test_http_error_status_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": False, "message": "server error"})

    with pytest.raises(PaystackRecipientError):
        await _client(handler).create_recipient(
            account_number=_ACCOUNT, bank_code="058", account_name="Ada A"
        )


async def test_non_json_body_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(PaystackRecipientError):
        await _client(handler).create_recipient(
            account_number=_ACCOUNT, bank_code="058", account_name="Ada A"
        )


async def test_secret_and_account_never_appear_in_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PaystackRecipientError) as exc:
        await _client(handler).create_recipient(
            account_number=_ACCOUNT, bank_code="058", account_name="Ada A"
        )
    assert _SECRET not in str(exc.value)
    assert _ACCOUNT not in str(exc.value)
