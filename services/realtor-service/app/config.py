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
    celery_result_backend: str = "redis://localhost:6379/1"

    # Realtor commission (SCRUM-74). On a completed deal the realtor who did the
    # inspection accrues a commission = commission_rate_bps/10_000 of the agreed
    # price (default 200 bps = 2%, CLAUDE.md §8). It's held 'pending' for
    # commission_available_business_days, then becomes 'available'. A Celery beat
    # accrues + releases; NO money moves here (escrow debit + disbursement are M3
    # / SCRUM-86). All amounts are BIGINT kobo.
    commission_rate_bps: int = 200
    commission_available_business_days: int = 3
    commission_beat_interval_seconds: float = 3600.0

    # Inspection auto-assignment (SCRUM-72). The nearest approved realtor within
    # the radius is assigned with an acceptance window; if none is in range the
    # request fails and an admin alert is logged.
    inspection_radius_meters: float = 50_000.0  # 50 km (AC)
    inspection_window_hours: int = 2

    # Inspection reassignment sweep (SCRUM-123). A Celery beat periodically finds
    # pending inspections whose acceptance window has lapsed and reassigns them to
    # the next-nearest approved realtor (excluding anyone who already declined),
    # resetting the window. When nobody else is in range the assignment is deferred
    # (window pushed out) and an admin alert is logged, so the sweep doesn't spin
    # on it every tick. Reuses inspection_radius_meters + inspection_window_hours.
    reassignment_beat_interval_seconds: float = 600.0  # every 10 min
    reassignment_batch_limit: int = 500
    reassignment_defer_hours: int = 2

    # Inspection report (SCRUM-73). The realtor's submitted GPS must be within
    # this radius of the property; at least min_photos photos are required.
    inspection_gps_radius_meters: float = 1_000.0  # 1 km (AC)
    inspection_min_photos: int = 3
    inspection_photo_max_bytes: int = 5 * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
