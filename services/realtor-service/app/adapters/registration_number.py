"""Maihomme registration-number issuance against auth-service (SCRUM-207).

When an admin approves a realtor, the platform issues the realtor a
`MH-R-000123` number and emails it to them; that number plus their password is
how they sign in from then on. The number is owned by AUTH-SERVICE because LOGIN
has to resolve it, and login is not this service's to serve (CLAUDE.md §3). This
adapter is the client side of `POST /internal/realtors/{id}/registration-number`.

Authentication is deliberately boring: it forwards the ADMIN'S OWN bearer token,
the token that authorised the approval in the first place. The mirror image of
auth-service's adapters/deals.py, and it means no service-to-service credential
had to be invented, nothing new to rotate, and the audit row auth-service writes
names the real admin rather than "realtor-service".

⚠️ FAIL CLOSED. Every failure — timeout, refused connection, 4xx, 5xx, an
unparseable body — raises `RegistrationNumberUnavailable`, and the review route
turns that into 503 WITHOUT committing the approval. An approved realtor with no
number cannot sign in at all and cannot be helped through the product: their
email login is refused precisely because they are approved. Leaving them pending
and asking the admin to click again a minute later is recoverable; the other
state is not. Issuance is idempotent on the auth side, so the retry is safe.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


def _normalise_base_url(raw: str) -> str:
    """Accept a bare `host:port` as well as a full URL.

    Render addresses private services as `<name>-<suffix>:8000` and exposes that
    through `fromService: { property: hostport }`, which yields "host:port" with
    NO scheme; Blueprint syntax gives no way to prepend one, and httpx rejects a
    scheme-less URL outright. Same fix, same reason, as auth-service's deal
    checker. http:// because this is an internal, private-network call.
    """
    trimmed = raw.strip().rstrip("/")
    if "://" not in trimmed:
        return f"http://{trimmed}"
    return trimmed


class RegistrationNumberUnavailable(RuntimeError):
    """auth-service could not issue the number. The caller MUST NOT proceed with
    the approval — this means "unknown", not "no number needed"."""


class RegistrationNumberIssuer(Protocol):
    async def issue(
        self, *, user_id: UUID, bearer_token: str
    ) -> str:  # pragma: no cover - protocol
        ...


class HttpRegistrationNumberIssuer:
    """Real client. Short timeout: an admin is watching a button spin, and a
    wrong answer is worse than a retry."""

    def __init__(self, *, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = _normalise_base_url(base_url)
        self._timeout = timeout_seconds

    async def issue(self, *, user_id: UUID, bearer_token: str) -> str:
        url = f"{self._base_url}/internal/realtors/{user_id}/registration-number"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url, headers={"Authorization": f"Bearer {bearer_token}"}
                )
        except httpx.HTTPError as exc:
            logger.warning("registration number issuance failed: %s", type(exc).__name__)
            raise RegistrationNumberUnavailable() from exc

        if response.status_code != 200:
            # Includes 401/403: if auth-service will not accept the admin's token
            # we have no number, and approving without one strands the realtor.
            logger.warning("registration number issuance returned %s", response.status_code)
            raise RegistrationNumberUnavailable()

        try:
            payload = response.json()
            number = payload["registration_number"]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("registration number body unusable: %s", type(exc).__name__)
            raise RegistrationNumberUnavailable() from exc
        if not isinstance(number, str) or not number:
            logger.warning("registration number body carried no number")
            raise RegistrationNumberUnavailable()
        return number


class InMemoryRegistrationNumberIssuer:
    """Test double + local/CI stand-in.

    Hands out sequential numbers in the real format, and remembers one per user
    so repeat calls are idempotent exactly as auth-service is. `fail_next`
    exercises the fail-closed path.

    ⚠️ Production MUST set `registration_number_use_fake=false`. With the fake
    bound, approvals appear to succeed and mint numbers that exist nowhere in
    auth-service — so the realtor's login would refuse the number they were
    emailed AND their email, which is a locked account with a cheerful
    notification attached. (The `DEAL_CHECK_USE_FAKE` lesson from SCRUM-188.)
    """

    def __init__(self, *, fail_next: bool = False) -> None:
        self.fail_next = fail_next
        self.issued: dict[UUID, str] = {}
        self.calls: list[tuple[UUID, str]] = []

    async def issue(self, *, user_id: UUID, bearer_token: str) -> str:
        self.calls.append((user_id, bearer_token))
        if self.fail_next:
            self.fail_next = False
            raise RegistrationNumberUnavailable()
        if user_id not in self.issued:
            self.issued[user_id] = f"MH-R-{len(self.issued) + 1:06d}"
        return self.issued[user_id]


def build_registration_number_issuer(
    *, use_fake: bool, base_url: str, timeout_seconds: float = 5.0
) -> RegistrationNumberIssuer:
    """Factory — in-memory fake for local/CI, real HTTP client otherwise."""
    if use_fake:
        return InMemoryRegistrationNumberIssuer()
    return HttpRegistrationNumberIssuer(base_url=base_url, timeout_seconds=timeout_seconds)
