"""NIN verification adapter — calls Ninja's identity API (SCRUM-218).

  * NinVerifier — Protocol every call site depends on.
  * NinjaNinVerifier — real adapter, calls Ninja's REST API.
  * InMemoryNinVerifier — in-process fake for local + CI.

We use ``mode: "verify"``, NOT ``mode: "lookup"``. Lookup returns the whole
registry record — mobile number, address state and a base64 photograph — which
is PII we have no need for and must not store (§4), travelling out of
af-south-1 to do it (§9). Verify returns a verdict plus per-field match scores
and nothing else.

CRITICAL: the plaintext NIN passes through here to reach Ninja but is NEVER
logged, and neither is the response body — ``fields[].provided`` echoes the
submitted name back, so logging the body would put PII in the log line. This is
the same trap SCRUM-175 hit when Twilio's error body turned out to contain the
plaintext OTP. Log lines carry status codes and field NAMES only.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

logger = logging.getLogger(__name__)

# Maps onto users.verified_status downstream: "verified" -> id_verified.
# "pending" is Ninja's `review` recommendation — a partial match a human should
# look at. It deliberately does NOT advance verified_status.
NinStatus = Literal["verified", "pending", "failed"]

# Ninja's three-way verdict, which is richer than the boolean this adapter used
# to return. `review` is the one that matters: a partially matching name is
# neither a pass nor a fraud signal on its own.
_RECOMMENDATION_TO_STATUS: dict[str, NinStatus] = {
    "accept": "verified",
    "review": "pending",
    "reject": "failed",
}


@dataclass(frozen=True)
class NinVerificationOutcome:
    status: NinStatus
    # Field NAMES that did not match, e.g. ("last_name",). Never the values:
    # Ninja echoes what we submitted in fields[].provided and that is PII.
    mismatches: tuple[str, ...] = ()


class NinVerificationError(RuntimeError):
    """Raised when the Ninja call itself fails (network/4xx/5xx) — distinct
    from a clean 'not verified' result."""


class NinVerifier(Protocol):
    async def verify(  # pragma: no cover - protocol
        self,
        nin: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> NinVerificationOutcome: ...


@dataclass
class InMemoryNinVerifier:
    """Test double. Records the call count and the NAMES it was asked to match
    (so tests can assert the split), but never the NIN."""

    outcome: NinVerificationOutcome = field(
        default_factory=lambda: NinVerificationOutcome(status="verified")
    )
    calls: int = 0
    fail_next: bool = False
    last_first_name: str | None = None
    last_last_name: str | None = None

    async def verify(
        self,
        nin: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> NinVerificationOutcome:
        self.calls += 1
        self.last_first_name = first_name
        self.last_last_name = last_name
        if self.fail_next:
            self.fail_next = False
            raise NinVerificationError("simulated provider failure")
        return self.outcome


class NinjaNinVerifier:
    """Calls Ninja's POST /api/identity/identify. The NIN is sent in the
    request body but never logged, and neither is the response body."""

    def __init__(self, *, api_url: str, secret_key: str, timeout_seconds: float = 5.0) -> None:
        self._secret_key = secret_key
        self._client = httpx.AsyncClient(base_url=api_url, timeout=timeout_seconds)

    async def verify(
        self,
        nin: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> NinVerificationOutcome:
        payload: dict[str, str] = {"idType": "nin", "mode": "verify", "idNumber": nin}
        # Omitted rather than sent blank: Ninja scores only the fields it is
        # given, so an absent name reads as "not checked" while an empty one
        # would score as a mismatch against every real record.
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name

        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/api/identity/identify",
                json=payload,
                headers={"Authorization": f"Bearer {self._secret_key}"},
            )
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            # str(exc) on a transport error carries the URL, never the body.
            logger.error(
                "nin.provider.failed",
                extra={"duration_ms": duration_ms, "error": str(exc)},
            )
            raise NinVerificationError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            self._log_error_status(response.status_code, duration_ms)
            raise NinVerificationError(f"ninja returned {response.status_code}")

        try:
            body = response.json()
        except ValueError as exc:
            logger.error("nin.provider.unparseable", extra={"duration_ms": duration_ms})
            raise NinVerificationError("ninja returned a non-JSON body") from exc
        if not isinstance(body, dict):
            logger.error("nin.provider.unparseable", extra={"duration_ms": duration_ms})
            raise NinVerificationError("ninja returned a non-object body")

        outcome = self._to_outcome(body)
        logger.info(
            "nin.provider.ok",
            extra={
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "outcome": outcome.status,
                # Names of the fields that disagreed, never their values.
                "mismatches": list(outcome.mismatches),
            },
        )
        return outcome

    @staticmethod
    def _log_error_status(status_code: int, duration_ms: float) -> None:
        """Separate log events for the failures that look identical inside a
        502 but need completely different responses from us."""
        if status_code == 402:
            # Prepaid balance exhausted. At ~NGN100 a check this silently
            # blocks ALL onboarding, so it has to be greppable on its own.
            logger.error("nin.provider.payment_required", extra={"duration_ms": duration_ms})
        elif status_code == 429:
            logger.error("nin.provider.rate_limited", extra={"duration_ms": duration_ms})
        else:
            logger.error(
                "nin.provider.error_status",
                extra={"status_code": status_code, "duration_ms": duration_ms},
            )

    @staticmethod
    def _to_outcome(body: dict[str, Any]) -> NinVerificationOutcome:
        raw_mismatches = body.get("mismatches")
        mismatches: tuple[str, ...] = (
            tuple(str(m) for m in raw_mismatches if isinstance(m, str))
            if isinstance(raw_mismatches, list)
            else ()
        )

        # An id that is not in the registry at all is a plain failure; there is
        # no verdict to read. `found` is only consulted when actually present.
        if "found" in body and not body.get("found"):
            return NinVerificationOutcome(status="failed")

        recommendation = str(body.get("recommendation") or "").strip().lower()
        status = _RECOMMENDATION_TO_STATUS.get(recommendation)
        if status is None:
            # No recommendation, or one we do not know — fall back to the
            # boolean. Treated as a two-way verdict, never as a pass.
            status = "verified" if bool(body.get("verified")) else "failed"
        return NinVerificationOutcome(status=status, mismatches=mismatches)

    async def aclose(self) -> None:
        await self._client.aclose()


def build_nin_verifier(
    *,
    use_fake: bool,
    api_url: str,
    secret_key: str,
    timeout_seconds: float,
) -> NinVerifier:
    """Factory — fake for local/CI, real Ninja client otherwise."""
    if use_fake:
        return InMemoryNinVerifier()
    return NinjaNinVerifier(api_url=api_url, secret_key=secret_key, timeout_seconds=timeout_seconds)
