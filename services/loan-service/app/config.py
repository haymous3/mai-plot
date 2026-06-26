"""Settings for the loan-service.

Reads from process env at import time; defaults let pytest run without exporting
anything. The JWT secret + issuer mirror auth-service: loan-service only DECODES
access tokens. Bank-partner API credentials live in env (CLAUDE.md §10:
BANK_<NNN>_API_URL / _API_KEY), never in the DB.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Admin endpoints require admin JWT AND an IP allowlist (CLAUDE.md). Kong
    # enforces the allowlist at the edge; this is defence in depth. Empty = any.
    admin_ip_allowlist: str = ""

    # Bank partner adapter (SCRUM-75). bank_adapter_enabled=false wires the FAKE
    # adapter (synthetic decisions, no network) so /loans/apply runs end-to-end in
    # dev/CI. The real HTTP adapter (SCRUM-76) is timeout-bounded + retried.
    bank_adapter_enabled: bool = False
    bank_request_timeout_seconds: float = 30.0  # AC: 30s max per call
    bank_max_retries: int = 3  # AC: 3 retries
    bank_retry_base_delay_seconds: float = 0.5  # exponential backoff base

    # Loan business rules (CLAUDE.md §8). Max loan = 50% of the agreed price;
    # a buyer may submit at most a few applications per day (Kong only rate-limits
    # 30/min — this is the per-buyer daily cap).
    loan_cap_bps: int = 5000  # 50%
    max_loan_applications_per_day: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
