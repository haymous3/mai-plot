"""Verification-email adapter: fake, ResendClient, factory (SCRUM-152)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.email_verification import (
    EmailDeliveryError,
    InMemoryEmailClient,
    ResendClient,
    VerificationEmail,
    build_email_verification_client,
)

_URL = "https://app.maihomme.com/verify-email?token=abc123"


@pytest.mark.asyncio
async def test_in_memory_captures_emails() -> None:
    client = InMemoryEmailClient()
    await client.send_verification(VerificationEmail(to="a@example.com", verify_url=_URL))
    assert len(client.sent) == 1
    assert client.sent[0].to == "a@example.com"
    assert client.sent[0].verify_url == _URL


@pytest.mark.asyncio
async def test_in_memory_fail_next_raises_and_clears() -> None:
    client = InMemoryEmailClient(fail_next=True)
    with pytest.raises(EmailDeliveryError):
        await client.send_verification(VerificationEmail(to="a@example.com", verify_url=_URL))
    assert client.fail_next is False
    await client.send_verification(VerificationEmail(to="a@example.com", verify_url=_URL))
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_resend_client_success_posts_expected_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "email_1"})

    client = ResendClient(api_key="re_key", from_address="Maihomme <no@maihomme.com>")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.resend.com",
        headers={"Authorization": "Bearer re_key"},
    )
    try:
        await client.send_verification(VerificationEmail(to="buyer@example.com", verify_url=_URL))
    finally:
        await client.aclose()

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_key"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["to"] == ["buyer@example.com"]
    assert payload["from"] == "Maihomme <no@maihomme.com>"
    # The magic link is embedded in both the html and text bodies.
    assert _URL in payload["html"]
    assert _URL in payload["text"]


@pytest.mark.asyncio
async def test_resend_client_raises_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "invalid"})

    client = ResendClient(api_key="re_key", from_address="no@maihomme.com")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.resend.com"
    )
    try:
        with pytest.raises(EmailDeliveryError):
            await client.send_verification(
                VerificationEmail(to="buyer@example.com", verify_url=_URL)
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_resend_client_wraps_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = ResendClient(api_key="re_key", from_address="no@maihomme.com")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.resend.com"
    )
    try:
        with pytest.raises(EmailDeliveryError):
            await client.send_verification(
                VerificationEmail(to="buyer@example.com", verify_url=_URL)
            )
    finally:
        await client.aclose()


def test_factory_picks_fake() -> None:
    client = build_email_verification_client(
        provider="resend",
        use_fake=True,
        api_key="",
        from_address="no@maihomme.com",
        timeout_seconds=1.0,
    )
    assert isinstance(client, InMemoryEmailClient)


def test_factory_picks_resend() -> None:
    client = build_email_verification_client(
        provider="resend",
        use_fake=False,
        api_key="k",
        from_address="no@maihomme.com",
        timeout_seconds=1.0,
    )
    assert isinstance(client, ResendClient)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        build_email_verification_client(
            provider="mailgun",
            use_fake=False,
            api_key="k",
            from_address="no@maihomme.com",
            timeout_seconds=1.0,
        )
