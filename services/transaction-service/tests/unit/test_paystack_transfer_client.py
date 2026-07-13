"""Unit tests for the real PaystackHttpTransferClient (SCRUM-145).

Exercises the payout/transfer client against an httpx.MockTransport so no network
is touched. A real Paystack transfer is asynchronous: POST /transfer answers with
data.status 'pending'/'otp'/'queued' (finished later by a transfer webhook),
'success' (immediate settle), or anything else (rejected). Covers each mapping,
every failure mode landing on PaystackTransferError, and asserts the secret key
never leaks into an error string.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.paystack import (
    PaystackHttpTransferClient,
    PaystackTransferError,
    TransferResult,
)

pytestmark = pytest.mark.asyncio

_SECRET = "sk_test_deadbeef"  # noqa: S105 - throwaway fake key for tests
_RECIPIENT = "RCP_abc123"
_REF = "pe-0001"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> PaystackHttpTransferClient:
    return PaystackHttpTransferClient(
        secret_key=_SECRET,
        base_url="https://api.paystack.co",
        transport=httpx.MockTransport(handler),
    )


async def test_pending_transfer_maps_to_pending() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {"status": "pending", "transfer_code": "TRF_xyz"},
            },
        )

    result = await _client(handler).transfer(
        reference_hint=_REF, amount_kobo=250_000, recipient_code=_RECIPIENT
    )

    assert result == TransferResult(reference="TRF_xyz", status="pending")
    assert captured["url"] == "https://api.paystack.co/transfer"
    assert captured["auth"] == f"Bearer {_SECRET}"
    assert captured["body"] == {
        "source": "balance",
        "amount": 250_000,
        "recipient": _RECIPIENT,
        "reference": _REF,
    }


async def test_success_transfer_maps_to_success() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": True, "data": {"status": "success", "transfer_code": "TRF_ok"}},
        )

    result = await _client(handler).transfer(
        reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
    )
    assert result == TransferResult(reference="TRF_ok", status="success")


async def test_unknown_status_maps_to_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": True, "data": {"status": "reversed", "transfer_code": "TRF_rev"}},
        )

    result = await _client(handler).transfer(
        reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
    )
    assert result == TransferResult(reference="TRF_rev", status="failed")


async def test_missing_transfer_code_falls_back_to_reference_hint() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": True, "data": {"status": "queued"}})

    result = await _client(handler).transfer(
        reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
    )
    assert result == TransferResult(reference=_REF, status="pending")


async def test_provider_status_false_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "message": "Insufficient balance"})

    with pytest.raises(PaystackTransferError) as exc:
        await _client(handler).transfer(
            reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
        )
    assert "Insufficient balance" in str(exc.value)


async def test_http_error_status_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": False, "message": "server error"})

    with pytest.raises(PaystackTransferError):
        await _client(handler).transfer(
            reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
        )


async def test_non_json_body_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(PaystackTransferError):
        await _client(handler).transfer(
            reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
        )


async def test_secret_never_appears_in_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PaystackTransferError) as exc:
        await _client(handler).transfer(
            reference_hint=_REF, amount_kobo=100, recipient_code=_RECIPIENT
        )
    assert _SECRET not in str(exc.value)
