"""Settings for the notification-service.

Reads from process env at import time; defaults match .env.example so a
developer can run pytest without exporting anything. The JWT secret + issuer
mirror auth-service: notification-service only DECODES access tokens.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://maiplot:change-me-local@localhost:5432/maiplot"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_issuer: str = "maiplot-platform"

    # Default page size for the in-app notification centre (SCRUM-82). The
    # client may request a smaller/larger page via ?limit, capped server-side.
    notification_page_size: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
