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

    # Listing media (SCRUM-22). Photos/videos are PUBLIC — stored in the media
    # bucket and served via CloudFront (cdn_url is precomputed at upload), NOT
    # via pre-signed URLs (that pattern is for private PoA/legal documents).
    # In-memory fake storage is the default so local/CI never reach S3.
    media_storage_use_fake: bool = True
    media_s3_bucket: str = "maiplot-media-local"
    media_s3_region: str = "af-south-1"
    media_s3_endpoint_url: str = ""
    cloudfront_domain: str = "cdn.maiplot.local"
    max_photo_bytes: int = 5 * 1024 * 1024
    max_video_bytes: int = 200 * 1024 * 1024
    max_photos_per_listing: int = 15
    max_videos_per_listing: int = 1

    # Listing search (SCRUM-22). All listing search runs on Elasticsearch
    # (CLAUDE.md non-negotiable) — never Postgres full-text. The in-memory
    # fake index is the default so local/CI never need an ES cluster; prod
    # sets search_use_fake=false + the real cluster URL.
    search_use_fake: bool = True
    elasticsearch_url: str = "http://localhost:9200"
    es_listings_index: str = "listings"

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
    expiry_beat_interval_seconds: float = 3600.0
    expiry_warning_window_hours: int = 48


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
