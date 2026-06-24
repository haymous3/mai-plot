"""Settings for the realtor-service.

Reads from process env at import time; defaults match .env.example so a
developer can run pytest without exporting anything. The JWT secret + issuer
mirror auth-service: realtor-service only DECODES access tokens.
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
    # enforces the allowlist at the edge; this app-level check is defence in
    # depth. Comma-separated IPs; empty = allow any (dev/test default).
    admin_ip_allowlist: str = ""

    # Government ID upload (SCRUM-71). A realtor's ID document goes to the PRIVATE
    # documents bucket (never public; served later only via short-TTL pre-signed
    # URLs). The in-memory fake is the default so local/CI never reach S3;
    # production sets gov_id_storage_use_fake=false + the real bucket/region.
    gov_id_storage_use_fake: bool = True
    gov_id_s3_bucket: str = "maiplot-documents-local"
    gov_id_s3_region: str = "af-south-1"
    gov_id_s3_endpoint_url: str = ""
    gov_id_max_upload_bytes: int = 10 * 1024 * 1024
    gov_id_presign_ttl_seconds: int = 900

    # Realtor decision notifications (SCRUM-71). The admin's approve/reject/suspend
    # is announced to the realtor via notification-service — realtor-service
    # enqueues the `notifications.dispatch` Celery task on the shared broker
    # (CLAUDE.md §3: cross-service async via Celery). Best-effort: a notification
    # failure never rolls back the committed decision. notifications_enabled=false
    # (dev/CI default) wires a no-op notifier so no broker is needed.
    notifications_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
