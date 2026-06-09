"""Settings for the auth-service.

Pydantic Settings reads from process env at import time. Defaults match
.env.example so a developer running `pytest` without exporting any vars
still gets a usable config (Postgres on localhost, OTP fake, etc.).

Tests that need to override a setting do so via env vars on the
`monkeypatch` fixture — there is no global mutable singleton to poke.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7
    jwt_issuer: str = "maiplot-platform"

    otp_expire_minutes: int = 5
    otp_rate_limit_per_hour: int = 5

    # Termii — the fake adapter is the default so local + CI runs work
    # without a sandbox API key. Production sets termii_use_fake=false
    # and provides the real key + base URL.
    termii_use_fake: bool = True
    termii_api_key: str = ""
    termii_sender_id: str = "Maiplot"
    termii_base_url: str = "https://api.ng.termii.com"
    termii_timeout_seconds: float = 3.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
