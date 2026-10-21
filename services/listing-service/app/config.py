"""Settings for the listing-service.

Pydantic Settings reads from process env at import time. Defaults match
.env.example so a developer running `pytest` without exporting any vars
still gets a usable config (Postgres on localhost, the shared JWT secret).

The JWT secret + issuer mirror auth-service: listing-service only DECODES
access tokens (it never mints them), so it shares the same HS256 secret and
issuer to verify tokens auth-service issued.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Cache TTLs (CLAUDE.md §6). Feed is short-lived; detail a little longer.
    feed_cache_ttl_seconds: int = 60
    listing_cache_ttl_seconds: int = 300

    # Listing media (SCRUM-22, reworked SCRUM-252). Photos/videos are public
    # content but live in a PRIVATE bucket (Railway has no public one), so the
    # stored URL is a stable listing-service link —
    # {media_public_base_url}/listings/media/{media_id} — which 302-redirects to
    # a pre-signed GET valid for media_presign_ttl_seconds. Set cloudfront_domain
    # only when a real PUBLIC CDN fronts the bucket; then the redirect goes there.
    # media_public_base_url must be the PUBLIC gateway (Kong) origin, because
    # browsers load these URLs straight from <img src>.
    # ⚠️ In-memory fake storage is the default so local/CI never reach S3 — and
    # until SCRUM-252 no deployed environment turned it off, so every listing
    # photo uploaded on Railway lived in one process's memory behind a
    # `https://cdn.maiplot.local/...` URL that no browser could load.
    media_storage_use_fake: bool = True
    media_s3_bucket: str = "maiplot-media-local"
    media_s3_region: str = "af-south-1"
    media_s3_endpoint_url: str = ""
    cloudfront_domain: str = ""
    media_presign_ttl_seconds: int = 3600
    media_public_base_url: str = "http://localhost:8000"
    max_photo_bytes: int = 5 * 1024 * 1024
    max_video_bytes: int = 200 * 1024 * 1024
    max_photos_per_listing: int = 15
    max_videos_per_listing: int = 1

    # Listing search backend (SCRUM-251). "postgres" (the default, everywhere)
    # queries property_listings directly: full-text on the generated
    # search_vector column + PostGIS for radius. Nothing to sync, so a listing is
    # searchable the moment its row commits. "elasticsearch" is kept behind this
    # switch for when scale needs it; "memory" is the per-process test double.
    # ⚠️ Before SCRUM-251 the default was the in-memory fake (search_use_fake)
    # and NO environment ever set it false — so production search ran on a
    # per-process dict and the Elasticsearch container sat unused.
    search_backend: Literal["postgres", "elasticsearch", "memory"] = "postgres"
    elasticsearch_url: str = "http://localhost:9200"
    es_listings_index: str = "listings"

    # Search relevance (SCRUM-115): distress listings are boosted in the default
    # relevance ranking, weighted by how soon they expire (a Gaussian decay over
    # expires_at). weight is the max boost added to a distress listing's score
    # (at/near expiry); scale_days is the decay half-point (boost halves once a
    # listing is this many days from expiry). Normal listings get no boost.
    search_urgency_boost_weight: float = 3.0
    search_urgency_scale_days: float = 7.0

    # Admin endpoints require admin JWT AND an IP whitelist (CLAUDE.md). Kong
    # enforces the IP allowlist at the edge; this app-level check is defence
    # in depth. Comma-separated IPs; empty = allow any (dev/test default —
    # production sets the real allowlist).
    admin_ip_allowlist: str = ""

    # Celery (CLAUDE.md: all async/background work via Celery + Redis). The
    # broker + result backend reuse the Redis instance. The expiry beat job
    # runs hourly; warnings fire 48h before a listing expires.
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"
    # SCRUM-249: prefork child processes per worker. Unset, Celery uses
    # os.cpu_count(), which inside a container is the HOST's core count — on
    # Railway that forked dozens of idle Python processes per worker (3–3.6 GB
    # each at 0.2% CPU, ~90% of the bill). Raise via CELERY_WORKER_CONCURRENCY.
    celery_worker_concurrency: int = 2
    expiry_beat_interval_seconds: float = 3600.0
    expiry_warning_window_hours: int = 48

    # Seller expiry-warning notification (SCRUM-112). The expiry worker enqueues
    # the notification-service `notifications.dispatch` task on the shared broker
    # when a listing is 48h from expiry. notifications_enabled=false (dev/CI
    # default) wires a no-op notifier so no broker is needed; production sets it
    # true (the broker is celery_broker_url above).
    notifications_enabled: bool = False

    # ES indexing (SCRUM-54). Only used when search_backend is "elasticsearch"
    # or "memory" — the postgres backend reads the row itself, so writes dispatch
    # nothing (SCRUM-251). On create / edit / status change the listing is
    # synced to Elasticsearch off the request path. In production
    # (index_via_celery=true) the write path enqueues a Celery task — index
    # failures retry with exponential backoff and never block the API. Local/CI
    # (the default) dispatch the same sync inline against the in-memory fake,
    # so search stays fresh without a broker or an ES cluster.
    index_via_celery: bool = False
    index_task_max_retries: int = 5
    index_task_retry_backoff_max_seconds: int = 600

    # view_count increment (SCRUM-114). A listing detail view bumps view_count
    # OFF the request path. In production (view_count_via_celery=true) the GET
    # enqueues a Celery task; local/CI increment inline against the request
    # session (no broker). Best-effort + approximate — a missed view is
    # acceptable (exact-once not required).
    view_count_via_celery: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
