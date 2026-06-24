"""Settings for the transaction-service.

Reads from process env at import time; defaults match .env.example so a
developer can run pytest without exporting anything. The JWT secret + issuer
mirror auth-service: transaction-service only DECODES access tokens.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Offer flow (SCRUM-66). An offer with no response auto-expires after this
    # window (business rule §4 — 72 hours). Enforced lazily on read/respond for
    # now; a Celery beat sweep is a follow-up.
    offer_expiry_hours: int = 72

    # Platform fee charged at deal close (SCRUM-119), in basis points
    # (250 = 2.5%). CLAUDE.md fixes the realtor commission at 2% (rule §7) but
    # never set Maiplot's own fee; this is admin/env tunable. The actual money
    # movement (net disbursement to the seller) is M3 / SCRUM-85.
    platform_fee_bps: int = 250

    # Escrow admin endpoints require admin JWT AND an IP whitelist (CLAUDE.md).
    # Kong enforces the allowlist at the edge; this app-level check is defence
    # in depth. Comma-separated IPs; empty = allow any (dev/test default).
    admin_ip_allowlist: str = ""

    # Cross-service notifications (SCRUM-117). When a buyer makes an offer, the
    # seller is alerted by enqueuing the notification-service `notifications.dispatch`
    # Celery task on the shared broker (CLAUDE.md §3: async work via Celery). The
    # send is best-effort — a broker hiccup never blocks or rolls back the offer.
    # notifications_enabled=false (the test/dev default) wires a no-op notifier so
    # no broker is needed; production sets it true + the broker URL.
    notifications_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
