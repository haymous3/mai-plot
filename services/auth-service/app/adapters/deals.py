"""Active-deal lookup against transaction-service (SCRUM-188).

The account-deletion guard has to know whether the caller still has a deal in
flight, and that fact lives in transaction-service. This is the FIRST
sibling-service call auth-service makes — every other adapter here talks to an
external provider (Twilio, Resend, the BVN/NIN bureaux).

Authentication is deliberately boring: the endpoint is CALLER-SCOPED
(`GET /transactions/active-deals` reads the subject from the JWT), so this
forwards the user's own bearer token. No service-to-service credential had to
be invented, and the call can see exactly what the user can see and no more.

⚠️ FAIL CLOSED. Every failure path — timeout, connection refused, 5xx, an
unparseable body — raises `DealCheckUnavailable`, and the route turns that into
503 rather than proceeding. Deleting an account whose escrow balance we could
not check is not recoverable through the product; making the user retry in a
minute is. This inverts the usual fail-open convention used for caches and rate
limiters, and the inversion is the point: those degrade a convenience, this
guards money (CLAUDE.md §9, CBN/AMLON).
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class DealCheckUnavailable(RuntimeError):
    """transaction-service could not be consulted. Callers MUST NOT treat this
    as "no active deals" — it means "unknown"."""


class DealChecker(Protocol):
    async def has_active_deals(self, *, bearer_token: str) -> bool:  # pragma: no cover
        ...


class HttpDealChecker:
    """Real client. Short timeout: this sits in front of a user-facing delete,
    and waiting is better than a wrong answer but not by much."""

    def __init__(self, *, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def has_active_deals(self, *, bearer_token: str) -> bool:
        url = f"{self._base_url}/transactions/active-deals"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url, headers={"Authorization": f"Bearer {bearer_token}"}
                )
        except httpx.HTTPError as exc:
            logger.warning("active-deal check failed: %s", type(exc).__name__)
            raise DealCheckUnavailable() from exc

        if response.status_code != 200:
            # Includes 401/403: if transaction-service will not accept the
            # token we cannot establish the user has nothing outstanding.
            logger.warning("active-deal check returned %s", response.status_code)
            raise DealCheckUnavailable()

        try:
            payload = response.json()
            return bool(payload["has_active"])
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("active-deal check body unusable: %s", type(exc).__name__)
            raise DealCheckUnavailable() from exc


class InMemoryDealChecker:
    """Test double. `has_active` is the answer; `fail_next` simulates the
    service being unreachable so the fail-closed path can be exercised."""

    def __init__(self, *, has_active: bool = False, fail_next: bool = False) -> None:
        self.has_active = has_active
        self.fail_next = fail_next
        self.calls: list[str] = []

    async def has_active_deals(self, *, bearer_token: str) -> bool:
        self.calls.append(bearer_token)
        if self.fail_next:
            self.fail_next = False
            raise DealCheckUnavailable()
        return self.has_active


def build_deal_checker(*, use_fake: bool, base_url: str) -> DealChecker:
    """Factory — in-memory fake for local/CI, real HTTP client otherwise."""
    if use_fake:
        return InMemoryDealChecker()
    return HttpDealChecker(base_url=base_url)
