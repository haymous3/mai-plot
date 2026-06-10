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

    # BVN verification (SCRUM-46). The fake verifier is default for local +
    # CI. bvn_pepper is the HMAC key for the deterministic bvn_lookup column
    # used for cross-account dedup — it is a server secret, NOT per-user,
    # and MUST be set to a strong random value in every real environment.
    bvn_use_fake: bool = True
    bvn_api_url: str = ""
    bvn_api_key: str = ""
    bvn_timeout_seconds: float = 5.0
    bvn_pepper: str = "change-me-to-a-long-random-bvn-pepper"

    # NIN verification (SCRUM-47). Same shape as BVN. nin_pepper is a
    # separate server secret for the deterministic nin_lookup dedup column.
    nin_use_fake: bool = True
    nin_api_url: str = ""
    nin_api_key: str = ""
    nin_timeout_seconds: float = 5.0
    nin_pepper: str = "change-me-to-a-long-random-nin-pepper"

    # PoA document upload (SCRUM-48). PoA sellers upload a Power-of-Attorney
    # document to the PRIVATE documents bucket; it is served later only via
    # short-TTL pre-signed URLs. The in-memory fake storage is the default so
    # local + CI never reach S3; production sets poa_storage_use_fake=false
    # plus the real bucket/region (endpoint_url is for localstack/minio dev).
    poa_storage_use_fake: bool = True
    poa_s3_bucket: str = "maiplot-documents-local"
    poa_s3_region: str = "af-south-1"
    poa_s3_endpoint_url: str = ""
    poa_max_upload_bytes: int = 10 * 1024 * 1024
    poa_presign_ttl_seconds: int = 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
