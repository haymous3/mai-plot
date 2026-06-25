"""Settings for the analytics-service.

Reads from process env at import time; defaults match the workspace dev DB so a
developer can run pytest without exporting anything. analytics-service only
DECODES access tokens (mirrors the other services).

Per data-model.md, analytics reads the READ REPLICA — `database_url` should point
at the replica DSN in production. In dev/CI there's no replica, so it defaults to
the primary. This service is read-only; it never writes.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # The read-replica DSN in production; the primary in dev/CI (no replica there).
    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Admin endpoints require admin JWT AND an IP allowlist (CLAUDE.md). Kong
    # enforces the allowlist at the edge; this app-level check is defence in
    # depth. Comma-separated IPs; empty = allow any (dev/test default).
    admin_ip_allowlist: str = ""

    # Audit-log viewer (SCRUM-126) pagination bounds.
    audit_default_page_size: int = 50
    audit_max_page_size: int = 200


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
