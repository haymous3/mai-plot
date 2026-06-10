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

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
