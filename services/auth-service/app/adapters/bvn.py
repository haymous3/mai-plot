"""BVN verification adapter — calls the identity bureau (NIBSS/partner).

Mirrors the Twilio adapter shape:
  * BvnVerifier — Protocol every call site depends on.
  * HttpBvnVerifier — real adapter, calls the bureau REST API.
  * InMemoryBvnVerifier — in-process fake for local + CI.

CRITICAL: the plaintext BVN passes through here to reach the bureau but is
NEVER logged. Log lines key off the result status and a request id only.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

logger = logging.getLogger(__name__)

# Maps onto users.verified_status downstream: "verified" -> id_verified.
BvnStatus = Literal["verified", "pending", "failed"]


@dataclass(frozen=True)
class BvnVerificationOutcome:
    status: BvnStatus


class BvnVerificationError(RuntimeError):
    """Raised when the bureau call itself fails (network/5xx) — distinct
    from a clean 'not verified' result."""


class BvnVerifier(Protocol):
    async def verify(self, bvn: str) -> BvnVerificationOutcome:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryBvnVerifier:
    """Test double. Records only the count of calls (never the BVN) and
    returns a configurable outcome."""

    outcome: BvnVerificationOutcome = field(
        default_factory=lambda: BvnVerificationOutcome(status="verified")
    )
    calls: int = 0
    fail_next: bool = False

    async def verify(self, bvn: str) -> BvnVerificationOutcome:
        self.calls += 1
        if self.fail_next:
            self.fail_next = False
            raise BvnVerificationError("simulated bureau failure")
        return self.outcome


class HttpBvnVerifier:
    """Calls the bureau's verify endpoint. The BVN is sent in the request
    body to the bureau but never logged."""

    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: float = 5.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(base_url=api_url, timeout=timeout_seconds)

    async def verify(self, bvn: str) -> BvnVerificationOutcome:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/verify/bvn",
                json={"bvn": bvn},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            # No BVN in the log — only timing + error class.
            logger.error(
                "bvn.bureau.failed",
                extra={"duration_ms": duration_ms, "error": str(exc)},
            )
            raise BvnVerificationError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "bvn.bureau.ok",
            extra={"status_code": response.status_code, "duration_ms": duration_ms},
        )
        if response.status_code >= 400:
            raise BvnVerificationError(f"bureau returned {response.status_code}")

        verified = bool(response.json().get("verified"))
        return BvnVerificationOutcome(status="verified" if verified else "failed")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_bvn_verifier(
    *,
    use_fake: bool,
    api_url: str,
    api_key: str,
    timeout_seconds: float,
) -> BvnVerifier:
    """Factory — fake for local/CI, real bureau client in production."""
    if use_fake:
        return InMemoryBvnVerifier()
    return HttpBvnVerifier(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
