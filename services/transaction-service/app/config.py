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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
