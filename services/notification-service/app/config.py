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

    # SMS via Termii (SCRUM-80). Termii is the critical-path channel (CLAUDE.md):
    # deal accepted, loan approved, inspection scheduled. The in-memory fake is
    # the default so local/CI never hit the network without a sandbox key;
    # production sets termii_use_fake=false + the real key.
    termii_use_fake: bool = True
    termii_api_key: str = ""
    termii_sender_id: str = "Maiplot"
    termii_base_url: str = "https://api.ng.termii.com"
    termii_timeout_seconds: float = 3.0

    # Celery (CLAUDE.md: all async/background work via Celery + Redis). The SMS
    # send runs off the request path. In production (sms_via_celery=true) the
    # dispatch enqueues the `send_sms_notification` task — a Termii outage retries
    # with exponential backoff and never blocks the caller. Local/CI (the default)
    # run the same send inline against the in-memory fake, so no broker is needed.
    sms_via_celery: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"
    sms_task_max_retries: int = 5
    sms_task_retry_backoff_max_seconds: int = 600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
