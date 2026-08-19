"""InMemoryTwilioClient and HttpTwilioClient happy/error paths (SCRUM-175)."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.twilio import (
    HttpTwilioClient,
    InMemoryTwilioClient,
    SmsError,
    build_sms_client,
)


@pytest.mark.asyncio
async def test_in_memory_captures_messages() -> None:
    client = InMemoryTwilioClient()
    await client.send_sms("+2348012345678", "hello")
    assert len(client.sent) == 1
    assert client.sent[0].phone == "+2348012345678"
    assert client.sent[0].message == "hello"


@pytest.mark.asyncio
async def test_in_memory_fail_next_raises_and_clears() -> None:
    client = InMemoryTwilioClient(fail_next=True)
    with pytest.raises(SmsError):
        await client.send_sms("+2348012345678", "x")
    assert client.fail_next is False
    # The next send works again.
    await client.send_sms("+2348012345678", "ok")
    assert len(client.sent) == 1


def _stub_client(handler: httpx.MockTransport) -> HttpTwilioClient:
    """Build a real client against a stub transport, so auth and form encoding
    are the production ones."""
    return HttpTwilioClient(
        account_sid="AC123",
        auth_token="tok",
        from_number="+15550001111",
        base_url="http://stub",
        timeout_seconds=1.0,
        transport=handler,
    )


@pytest.mark.asyncio
async def test_http_client_success_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"sid": "SM123", "status": "queued"})

    real = _stub_client(httpx.MockTransport(handler))
    try:
        await real.send_sms("+2348012345678", "hi")
    finally:
        await real.aclose()


@pytest.mark.asyncio
async def test_http_client_posts_twilio_message_shape() -> None:
    """Twilio wants form-encoded To/From/Body at the Accounts/{sid}/Messages
    path, with the recipient in full E.164 (leading + kept — the opposite of
    what Termii wanted)."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = request.content.decode()
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(201, json={"sid": "SM123"})

    real = _stub_client(httpx.MockTransport(handler))
    try:
        await real.send_sms("+2348012345678", "Your code is 123456")
    finally:
        await real.aclose()

    assert captured["path"] == "/2010-04-01/Accounts/AC123/Messages.json"
    assert "application/x-www-form-urlencoded" in str(captured["content_type"])
    body = str(captured["body"])
    assert "To=%2B2348012345678" in body
    assert "From=%2B15550001111" in body
    # HTTP Basic auth, Account SID as user / Auth Token as password.
    assert str(captured["auth"]).startswith("Basic ")


@pytest.mark.asyncio
async def test_http_client_raises_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 21211, "message": "invalid To"})

    real = _stub_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(SmsError):
            await real.send_sms("+2348012345678", "hi")
    finally:
        await real.aclose()


@pytest.mark.asyncio
async def test_http_client_error_does_not_leak_otp() -> None:
    """The failure message must not echo Twilio's body back — Twilio returns
    the message Body in its payload, which carries the plaintext OTP."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"body": "Your Maiplot verification code is 424242"})

    real = _stub_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(SmsError) as exc:
            await real.send_sms("+2348012345678", "Your Maiplot verification code is 424242")
    finally:
        await real.aclose()
    assert "424242" not in str(exc.value)


@pytest.mark.asyncio
async def test_http_client_wraps_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    real = _stub_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(SmsError):
            await real.send_sms("+2348012345678", "hi")
    finally:
        await real.aclose()


def test_factory_picks_fake() -> None:
    client = build_sms_client(
        use_fake=True,
        account_sid="",
        auth_token="",
        from_number="",
        base_url="http://x",
        timeout_seconds=1.0,
    )
    assert isinstance(client, InMemoryTwilioClient)


def test_factory_picks_real() -> None:
    client = build_sms_client(
        use_fake=False,
        account_sid="AC123",
        auth_token="tok",
        from_number="+15550001111",
        base_url="http://x",
        timeout_seconds=1.0,
    )
    assert isinstance(client, HttpTwilioClient)
