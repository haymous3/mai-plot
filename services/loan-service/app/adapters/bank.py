"""Bank partner adapter layer (SCRUM-75) — §11.

Every bank integration implements `BankPartnerAdapter`. A registry resolves the
adapter for a given partner. External calls go through `call_with_resilience`:
a 30s timeout per call, up to 3 exponential-backoff retries, every attempt logged
with its duration + outcome (the AC).

  * FakeBankAdapter — synthetic decisions, no network. The dev/CI/test default so
    /loans/apply runs end-to-end without a real bank.
  * BankHttpAdapter — real HTTP integration (deferred to SCRUM-76); credentials
    come from env (CLAUDE.md §10: BANK_<NNN>_API_URL / _API_KEY), never the DB.

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

logger = logging.getLogger(__name__)


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
    """Real bank-partner HTTP integration — deferred to SCRUM-76. Wraps every
    call in call_with_resilience (timeout + retries + logging)."""

    def __init__(
        self, *, base_url: str, api_key: str, timeout: float, retries: int, base_delay: float
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._retries = retries
        self._base_delay = base_delay

    async def submit_application(
        self, application: BankApplication
    ) -> LoanSubmission:  # pragma: no cover - unbuilt
        raise NotImplementedError("Real bank submission lands in SCRUM-76.")

    async def get_status(self, bank_reference_id: str) -> LoanStatusResult:  # pragma: no cover
        raise NotImplementedError("Real bank status lands in SCRUM-76.")

    async def open_account(self, buyer_id: UUID) -> AccountOpenResult:  # pragma: no cover
        raise NotImplementedError("Real bank account opening lands in SCRUM-76.")


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
