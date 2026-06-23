"""Termii adapter — SMS dispatch for critical notification alerts (SCRUM-80).

Three pieces:
  * TermiiClient — Protocol every callable site depends on.
  * HttpTermiiClient — real adapter, calls Termii's REST API.
  * InMemoryTermiiClient — in-process fake. Captures (phone, message)
    pairs so tests can assert what was sent without hitting the network.

Production binds the real one via TERMII_USE_FAKE=false. CI and local dev get
the fake by default, matching .env.example. This mirrors auth-service's Termii
adapter (OTP / PoA decision SMS) — the same proven client, reused here so the
notification-service owns the orchestration while the transport stays identical.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class TermiiClient(Protocol):
    async def send_sms(self, phone: str, message: str) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class SentMessage:
    phone: str
    message: str


class TermiiError(RuntimeError):
    """Raised when Termii rejects or fails to deliver a dispatch."""


@dataclass
class InMemoryTermiiClient:
    """Test double — captures sent messages in-process.

    Construct fresh per test (the dispatch service accepts the client by
    injection) so there is no global state to clear between tests."""

    sent: list[SentMessage] = field(default_factory=list)
    fail_next: bool = False

    async def send_sms(self, phone: str, message: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise TermiiError("simulated Termii failure")
        self.sent.append(SentMessage(phone=phone, message=message))


class HttpTermiiClient:
    """Calls Termii's send endpoint. One client per service process; httpx
    handles connection pooling under the hood."""

    def __init__(
        self,
        *,
        api_key: str,
        sender_id: str,
        base_url: str,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._api_key = api_key
        self._sender_id = sender_id
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def send_sms(self, phone: str, message: str) -> None:
        # Termii's `to` field expects the number without the leading +.
        payload = {
            "to": phone.lstrip("+"),
            "from": self._sender_id,
            "sms": message,
            "type": "plain",
            "channel": "generic",
            "api_key": self._api_key,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post("/api/sms/send", json=payload)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "termii.dispatch.failed",
                extra={"phone_suffix": phone[-4:], "duration_ms": duration_ms, "error": str(exc)},
            )
            raise TermiiError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "termii.dispatch.ok",
            extra={
                "phone_suffix": phone[-4:],
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        if response.status_code >= 400:
            raise TermiiError(f"termii returned {response.status_code}: {response.text[:200]}")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_termii_client(
    *,
    use_fake: bool,
    api_key: str,
    sender_id: str,
    base_url: str,
    timeout_seconds: float,
) -> TermiiClient:
    """Factory — pick the fake or real client based on settings."""
    if use_fake:
        return InMemoryTermiiClient()
    return HttpTermiiClient(
        api_key=api_key,
        sender_id=sender_id,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
