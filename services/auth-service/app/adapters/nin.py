"""NIN verification adapter — calls the identity bureau (NIMC/partner).

Mirrors app/adapters/bvn.py:
  * NinVerifier — Protocol every call site depends on.
  * HttpNinVerifier — real adapter, calls the bureau REST API.
  * InMemoryNinVerifier — in-process fake for local + CI.

CRITICAL: the plaintext NIN passes through here to reach the bureau but
is NEVER logged. Log lines key off the result status only.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

logger = logging.getLogger(__name__)

# Maps onto users.verified_status downstream: "verified" -> id_verified.
NinStatus = Literal["verified", "pending", "failed"]


@dataclass(frozen=True)
class NinVerificationOutcome:
    status: NinStatus


class NinVerificationError(RuntimeError):
    """Raised when the bureau call itself fails (network/5xx) — distinct
    from a clean 'not verified' result."""


class NinVerifier(Protocol):
    async def verify(self, nin: str) -> NinVerificationOutcome:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryNinVerifier:
    """Test double. Records only the call count (never the NIN) and returns
    a configurable outcome."""

    outcome: NinVerificationOutcome = field(
        default_factory=lambda: NinVerificationOutcome(status="verified")
    )
    calls: int = 0
    fail_next: bool = False

    async def verify(self, nin: str) -> NinVerificationOutcome:
        self.calls += 1
        if self.fail_next:
            self.fail_next = False
            raise NinVerificationError("simulated bureau failure")
        return self.outcome


class HttpNinVerifier:
    """Calls the bureau's verify endpoint. The NIN is sent in the request
    body but never logged."""

    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: float = 5.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(base_url=api_url, timeout=timeout_seconds)

    async def verify(self, nin: str) -> NinVerificationOutcome:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/verify/nin",
                json={"nin": nin},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "nin.bureau.failed",
                extra={"duration_ms": duration_ms, "error": str(exc)},
            )
            raise NinVerificationError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "nin.bureau.ok",
            extra={"status_code": response.status_code, "duration_ms": duration_ms},
        )
        if response.status_code >= 400:
            raise NinVerificationError(f"bureau returned {response.status_code}")

        verified = bool(response.json().get("verified"))
        return NinVerificationOutcome(status="verified" if verified else "failed")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_nin_verifier(
    *,
    use_fake: bool,
    api_url: str,
    api_key: str,
    timeout_seconds: float,
) -> NinVerifier:
    """Factory — fake for local/CI, real bureau client in production."""
    if use_fake:
        return InMemoryNinVerifier()
    return HttpNinVerifier(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
