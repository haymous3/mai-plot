"""InMemoryTermiiClient and HttpTermiiClient happy/error paths."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.termii import (
    HttpTermiiClient,
    InMemoryTermiiClient,
    TermiiError,
    build_termii_client,
)


@pytest.mark.asyncio
async def test_in_memory_captures_messages() -> None:
    client = InMemoryTermiiClient()
    await client.send_sms("+2348012345678", "hello")
    assert len(client.sent) == 1
    assert client.sent[0].phone == "+2348012345678"
    assert client.sent[0].message == "hello"


@pytest.mark.asyncio
async def test_in_memory_fail_next_raises_and_clears() -> None:
    client = InMemoryTermiiClient(fail_next=True)
    with pytest.raises(TermiiError):
        await client.send_sms("+2348012345678", "x")
    assert client.fail_next is False
    # The next send works again.
    await client.send_sms("+2348012345678", "ok")
    assert len(client.sent) == 1


@pytest.mark.asyncio
async def test_http_client_success_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message_id": "abc"})

    transport = httpx.MockTransport(handler)
    real = HttpTermiiClient(
        api_key="k", sender_id="Maiplot", base_url="http://stub", timeout_seconds=1.0
    )
    real._client = httpx.AsyncClient(transport=transport, base_url="http://stub")
    try:
        await real.send_sms("+2348012345678", "hi")
    finally:
        await real.aclose()


@pytest.mark.asyncio
async def test_http_client_raises_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    transport = httpx.MockTransport(handler)
    real = HttpTermiiClient(
        api_key="k", sender_id="Maiplot", base_url="http://stub", timeout_seconds=1.0
    )
    real._client = httpx.AsyncClient(transport=transport, base_url="http://stub")
    try:
        with pytest.raises(TermiiError):
            await real.send_sms("+2348012345678", "hi")
    finally:
        await real.aclose()


def test_factory_picks_fake() -> None:
    client = build_termii_client(
        use_fake=True,
        api_key="",
        sender_id="Maiplot",
        base_url="http://x",
        timeout_seconds=1.0,
    )
    assert isinstance(client, InMemoryTermiiClient)


def test_factory_picks_real() -> None:
    client = build_termii_client(
        use_fake=False,
        api_key="k",
        sender_id="Maiplot",
        base_url="http://x",
        timeout_seconds=1.0,
    )
    assert isinstance(client, HttpTermiiClient)
