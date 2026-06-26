"""Bank partner adapter layer (SCRUM-75) — §11.

Every bank integration implements `BankPartnerAdapter`. A registry resolves the
adapter for a given partner. External calls go through `call_with_resilience`:
a 30s timeout per call, up to 3 exponential-backoff retries, every attempt logged
with its duration + outcome (the AC).

  * FakeBankAdapter — synthetic decisions, no network. The dev/CI/test default so
    /loans/apply runs end-to-end without a real bank.
  * BankHttpAdapter — real HTTP integration (SCRUM-76): submit/get_status/
    open_account over httpx, every call wrapped in call_with_resilience.
    Credentials come from env (CLAUDE.md §10: <SHORT_CODE>_API_URL / _API_KEY),
    never the DB.

Amounts are BIGINT kobo (CLAUDE.md). API keys are never logged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# Map a bank partner's status vocabulary onto our loans.status values. Unknown
# strings are treated as still-in-review rather than guessing a decision.
_STATUS_MAP = {
    "submitted": "under_review",
    "received": "under_review",
    "pending": "under_review",
    "processing": "under_review",
    "under_review": "under_review",
    "in_review": "under_review",
    "approved": "approved",
    "accepted": "approved",
    "rejected": "rejected",
    "declined": "rejected",
    "info_required": "info_required",
    "more_info": "info_required",
}


def map_bank_status(raw: object) -> str:
    """Normalise a bank's status string to a loans.status value."""
    return _STATUS_MAP.get(str(raw).strip().lower(), "under_review")


class BankAdapterError(RuntimeError):
    """A bank partner API call failed (network / timeout / provider error)."""


@dataclass(frozen=True)
class BankApplication:
    loan_id: UUID
    buyer_id: UUID
    transaction_id: UUID
    requested_amount_kobo: int
    tenure_months: int


@dataclass(frozen=True)
class LoanSubmission:
    bank_reference_id: str
    status: str  # a loans.status value, e.g. 'under_review'


@dataclass(frozen=True)
class LoanStatusResult:
    status: str
    approved_amount_kobo: int | None = None
    interest_rate_bps: int | None = None
    tenure_months: int | None = None
    monthly_instalment_kobo: int | None = None


@dataclass(frozen=True)
class AccountOpenResult:
    account_reference: str


async def call_with_resilience[T](
    op: Callable[[], Awaitable[T]],
    *,
    op_name: str,
    retries: int,
    base_delay: float,
    timeout: float,
) -> T:
    """Run a bank API call with a per-call timeout + exponential-backoff retries,
    logging every attempt's duration + outcome. Raises BankAdapterError once all
    attempts are exhausted."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(op(), timeout=timeout)
        except Exception as exc:  # timeout / HTTP / provider error
            duration_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "bank.call_failed",
                extra={"op": op_name, "attempt": attempt, "duration_ms": duration_ms},
            )
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(base_delay * (2**attempt))
            continue
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "bank.call_ok",
            extra={"op": op_name, "attempt": attempt, "duration_ms": duration_ms},
        )
        return result
    raise BankAdapterError(f"{op_name} failed after {retries + 1} attempts") from last_exc


class BankPartnerAdapter(Protocol):
    async def submit_application(
        self, application: BankApplication
    ) -> LoanSubmission:  # pragma: no cover - protocol
        ...

    async def get_status(self, bank_reference_id: str) -> LoanStatusResult:  # pragma: no cover
        ...

    async def open_account(self, buyer_id: UUID) -> AccountOpenResult:  # pragma: no cover
        ...


class FakeBankAdapter:
    """In-process fake — accepts the application into review, no network."""

    async def submit_application(self, application: BankApplication) -> LoanSubmission:
        return LoanSubmission(
            bank_reference_id=f"FAKE-BANK-{application.loan_id}", status="under_review"
        )

    async def get_status(self, bank_reference_id: str) -> LoanStatusResult:
        return LoanStatusResult(status="under_review")

    async def open_account(self, buyer_id: UUID) -> AccountOpenResult:
        return AccountOpenResult(account_reference=f"FAKE-ACCT-{buyer_id}")


class BankHttpAdapter:
    """Real bank-partner HTTP integration (SCRUM-76). Every call goes through
    call_with_resilience (per-call timeout + retries + logging). The bank's API
    key is sent as a bearer token and is never logged. `transport` is injectable
    so tests can drive the adapter without a live bank."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float,
        retries: int,
        base_delay: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._retries = retries
        self._base_delay = base_delay
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def _resilient[T](self, op: Callable[[], Awaitable[T]], *, op_name: str) -> T:
        return await call_with_resilience(
            op,
            op_name=op_name,
            retries=self._retries,
            base_delay=self._base_delay,
            timeout=self._timeout,
        )

    async def submit_application(self, application: BankApplication) -> LoanSubmission:
        async def _op() -> LoanSubmission:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url}/v1/loans",
                    json={
                        "client_reference": str(application.loan_id),
                        "buyer_id": str(application.buyer_id),
                        "transaction_id": str(application.transaction_id),
                        "amount_kobo": application.requested_amount_kobo,
                        "tenure_months": application.tenure_months,
                    },
                )
                resp.raise_for_status()
                body = resp.json()
            return LoanSubmission(
                bank_reference_id=str(body["reference"]),
                status=map_bank_status(body.get("status")),
            )

        return await self._resilient(_op, op_name="submit_application")

    async def get_status(self, bank_reference_id: str) -> LoanStatusResult:
        async def _op() -> LoanStatusResult:
            async with self._client() as client:
                resp = await client.get(f"{self._base_url}/v1/loans/{bank_reference_id}")
                resp.raise_for_status()
                body = resp.json()
            return LoanStatusResult(
                status=map_bank_status(body.get("status")),
                approved_amount_kobo=_as_int(body.get("approved_amount_kobo")),
                interest_rate_bps=_as_int(body.get("interest_rate_bps")),
                tenure_months=_as_int(body.get("tenure_months")),
                monthly_instalment_kobo=_as_int(body.get("monthly_instalment_kobo")),
            )

        return await self._resilient(_op, op_name="get_status")

    async def open_account(self, buyer_id: UUID) -> AccountOpenResult:
        async def _op() -> AccountOpenResult:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url}/v1/accounts", json={"buyer_id": str(buyer_id)}
                )
                resp.raise_for_status()
                body = resp.json()
            return AccountOpenResult(account_reference=str(body["account_reference"]))

        return await self._resilient(_op, op_name="open_account")


def _as_int(value: object) -> int | None:
    """Coerce a bank-supplied numeric field to int, or None if absent/invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def resolve_bank_credentials(short_code: str) -> tuple[str, str]:
    """Read a partner's API URL + key from env (CLAUDE.md §10:
    <SHORT_CODE>_API_URL / _API_KEY). Secrets never live in the DB."""
    prefix = short_code.upper()
    return os.environ.get(f"{prefix}_API_URL", ""), os.environ.get(f"{prefix}_API_KEY", "")


@dataclass(frozen=True)
class _AdapterConfig:
    enabled: bool
    timeout: float
    retries: int
    base_delay: float


class BankAdapterRegistry:
    """Resolves the adapter for a bank partner, memoised by short_code."""

    def __init__(self, config: _AdapterConfig) -> None:
        self._config = config
        self._cache: dict[str, BankPartnerAdapter] = {}

    def for_partner(self, *, short_code: str) -> BankPartnerAdapter:
        if short_code not in self._cache:
            if not self._config.enabled:
                self._cache[short_code] = FakeBankAdapter()
            else:
                base_url, api_key = resolve_bank_credentials(short_code)
                self._cache[short_code] = BankHttpAdapter(
                    base_url=base_url,
                    api_key=api_key,
                    timeout=self._config.timeout,
                    retries=self._config.retries,
                    base_delay=self._config.base_delay,
                )
        return self._cache[short_code]


def build_bank_adapter_registry(
    *, enabled: bool, timeout: float, retries: int, base_delay: float
) -> BankAdapterRegistry:
    return BankAdapterRegistry(
        _AdapterConfig(enabled=enabled, timeout=timeout, retries=retries, base_delay=base_delay)
    )
