"""Unit tests for the real PaystackHttpChargeClient (SCRUM-133).

Exercises the collection client against an httpx.MockTransport so no network is
touched. Covers the happy path plus every failure mode mapping to
PaystackChargeError, and asserts the secret never leaks into an error string.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.paystack_charge import (
    CheckoutInit,
    PaystackChargeError,
    PaystackHttpChargeClient,
)

pytestmark = pytest.mark.asyncio

_SECRET = "sk_test_deadbeef"  # noqa: S105 - throwaway fake key for tests


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> PaystackHttpChargeClient:
    return PaystackHttpChargeClient(
        secret_key=_SECRET,
        base_url="https://api.paystack.co",
        transport=httpx.MockTransport(handler),
    )


async def test_initialize_returns_checkout_url() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/abc123",
                    "reference": "pe-ref-1",
                },
            },
        )

    result = await _client(handler).initialize(
        reference="pe-ref-1", amount_kobo=5_000_00, email="buyer@maiplot.ng", callback_url=None
    )

    assert result == CheckoutInit(
        authorization_url="https://checkout.paystack.com/abc123", reference="pe-ref-1"
    )
    assert captured["url"] == "https://api.paystack.co/transaction/initialize"
    assert captured["auth"] == f"Bearer {_SECRET}"
    # Amount is passed through as kobo (Paystack NGN amounts are in kobo).
    assert captured["body"] == {
        "reference": "pe-ref-1",
        "amount": 5_000_00,
        "email": "buyer@maiplot.ng",
    }


async def test_callback_url_included_when_supplied() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/x"}},
        )

    await _client(handler).initialize(
        reference="r", amount_kobo=100, email="b@x.ng", callback_url="https://maiplot.ng/return"
    )
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["callback_url"] == "https://maiplot.ng/return"


async def test_reference_falls_back_to_request_when_absent() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": True, "data": {"authorization_url": "https://checkout.paystack.com/y"}},
        )

    result = await _client(handler).initialize(
        reference="fallback-ref", amount_kobo=100, email="b@x.ng", callback_url=None
    )
    assert result.reference == "fallback-ref"


async def test_provider_status_false_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "message": "Invalid email address"})

    with pytest.raises(PaystackChargeError) as exc:
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="bad", callback_url=None
        )
    assert "Invalid email address" in str(exc.value)


async def test_success_body_missing_authorization_url_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": True, "data": {"reference": "r"}})

    with pytest.raises(PaystackChargeError):
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="b@x.ng", callback_url=None
        )


async def test_http_error_status_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": False, "message": "server error"})

    with pytest.raises(PaystackChargeError):
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="b@x.ng", callback_url=None
        )


async def test_network_error_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PaystackChargeError):
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="b@x.ng", callback_url=None
        )


async def test_non_json_body_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(PaystackChargeError):
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="b@x.ng", callback_url=None
        )


async def test_secret_never_appears_in_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PaystackChargeError) as exc:
        await _client(handler).initialize(
            reference="r", amount_kobo=100, email="b@x.ng", callback_url=None
        )
    assert _SECRET not in str(exc.value)
