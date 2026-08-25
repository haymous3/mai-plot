"""Settings for the auth-service.

Pydantic Settings reads from process env at import time. Defaults match
.env.example so a developer running `pytest` without exporting any vars
still gets a usable config (Postgres on localhost, OTP fake, etc.).

Tests that need to override a setting do so via env vars on the
`monkeypatch` fixture — there is no global mutable singleton to poke.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Deployment environment: local | staging | production. Set by
    # docker-compose (local) and by the maiplot-shared env group (staging).
    # Load-bearing for security, not just logging: app/routes/dev.py is only
    # mounted when this is exactly "local", so the dev-only OTP reader cannot
    # exist anywhere else. Do not default this to anything but "local" — a
    # permissive default would be safe here (it only ever ENABLES a dev tool on
    # a developer's own machine) but any other value would silently disable it.
    env: str = "local"

    @field_validator("env", mode="after")
    @classmethod
    def _strip_dotenv_comment(cls, value: str) -> str:
        """Strip an inline `# comment` and surrounding whitespace.

        pydantic-settings does NOT strip inline comments from string values, so
        `.env`'s `ENV=local   # local | staging | production` arrives as the
        whole 60-character line. That silently broke the `env == "local"` gate
        in app/routes/dev.py — the dev routes never registered.

        Stripping here rather than only fixing `.env` because `.env.example`
        ships the same comment style and every developer copies it. Note this
        only ever NARROWS a value ("staging  # x" -> "staging"); it can never
        turn a non-local value into "local", so it cannot widen the gate.
        """
        return value.split("#", 1)[0].strip()

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7
    jwt_issuer: str = "maiplot-platform"

    otp_expire_minutes: int = 5
    otp_rate_limit_per_hour: int = 5
    # Failed guesses allowed per code before it is burnt (SCRUM-176). A 6-digit
    # code is brute forceable inside its 5-minute window if guesses are free.
    # The counter lives in Redis and fails open, so this degrades to the old
    # uncapped behaviour rather than locking users out during an outage.
    otp_max_attempts: int = 3

    # Twilio (SCRUM-175, replaced Termii) — the fake adapter is the default so
    # local + CI runs work without real credentials. Production sets
    # twilio_use_fake=false and provides the real Account SID + Auth Token.
    #
    # NOTE (SCRUM-175 deliverability): twilio_from_number is a US long code
    # while every recipient is a Nigerian mobile. Nigerian carriers filter A2P
    # long-code traffic; a registered alphanumeric sender ID is the fix. Twilio
    # accepting a message is not evidence it was delivered.
    twilio_use_fake: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_base_url: str = "https://api.twilio.com"
    twilio_timeout_seconds: float = 3.0

    # Email verification (SCRUM-152). Account verification is an email magic
    # link, not phone OTP. The in-memory fake sender is the default so local +
    # CI never hit the network; production sets email_verification_use_fake=false
    # and the real provider key. Provider-agnostic: `email_provider` selects the
    # adapter (Resend for V1; an SES adapter slots into the factory later).
    #
    # NOTE (CLAUDE.md §9 residency): Resend is a US provider, so verification
    # emails leave af-south-1. The product owner accepted this trade-off for V1;
    # swapping email_provider to an af-south-1-resident sender (SES) closes it.
    email_verification_use_fake: bool = True
    email_provider: str = "resend"
    resend_api_key: str = ""
    # The brand is Maihomme; maihomme.com is the domain verified in Resend
    # (2026-08-25, eu-west-1). "maiplot" was never a registered domain — it was
    # an aspirational placeholder that survived in config, and sending from it
    # fails outright because Resend only accepts verified domains.
    email_from_address: str = "Maihomme <noreply@maihomme.com>"
    email_timeout_seconds: float = 5.0
    email_verification_expire_minutes: int = 30
    # Base URL of the frontend landing page the magic link points at; the token
    # is appended as ?token=... and the page POSTs it to /auth/verify/email.
    # ⚠️ app.maihomme.com does NOT resolve yet — the apex is a GoDaddy site
    # builder and there is no `app` record. Point it at the deployed frontend
    # (Vercel) before relying on this in staging or production, or every
    # verification link 404s. Overridden per environment; this default exists so
    # local runs have something coherent.
    email_verification_base_url: str = "https://app.maihomme.com/verify-email"

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

    # PoA review queue (SCRUM-56). The legal team reviews PoA documents via
    # admin endpoints gated to the `legal_team` role AND an IP allowlist
    # (CLAUDE.md: admin endpoints require JWT + IP whitelist). Kong enforces the
    # allowlist at the edge; this app-level check is defence in depth.
    # Comma-separated IPs; empty = allow any (dev/test default).
    legal_team_ip_allowlist: str = ""

    # PoA decision notifications (SCRUM-113). The legal team's approve/reject is
    # announced to the seller (in-app + SMS + email) via notification-service —
    # auth-service enqueues the `notifications.dispatch` Celery task on the shared
    # broker rather than calling Termii inline (CLAUDE.md §3: cross-service async
    # via Celery). Best-effort: a notification failure never rolls back the
    # committed decision. notifications_enabled=false (dev/CI default) wires a
    # no-op notifier so no broker is needed.
    notifications_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
