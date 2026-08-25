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

    # Notification archive sweep (SCRUM-120). A Celery beat stamps archived_at on
    # notifications older than the retention window so the in-app centre stays
    # lean; rows are retained (not deleted). Runs daily by default.
    notification_retention_days: int = 90
    notification_archive_beat_interval_seconds: float = 86400.0  # daily

    # Web Push (SCRUM-79). In-browser push via the Web Push Protocol + VAPID
    # (replaces FCM in Phase 1). The in-memory fake is the default so local/CI
    # never need real VAPID keys or a push service; production sets
    # web_push_use_fake=false + a real VAPID keypair (base64url, generated once
    # with py-vapid). vapid_subject is the contact mailto:/URL push services
    # require. push_ttl_seconds is how long a push service holds an undelivered
    # message for an offline browser.
    web_push_use_fake: bool = True
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:ops@maihomme.com"
    push_ttl_seconds: int = 86400
    push_via_celery: bool = False
    push_task_max_retries: int = 5
    push_task_retry_backoff_max_seconds: int = 600

    # Email via AWS SES (SCRUM-81). For document actions + transaction milestones
    # (informational, not the critical path). The in-memory fake is the default
    # so local/CI never hit AWS; production sets ses_use_fake=false + a verified
    # ses_from_email on the maihomme.com domain. unsubscribe_base_url is the page a
    # recipient's unsubscribe link points at (NDPR); the link carries the user id
    # — the unsubscribe endpoint + preference honouring are the preferences-API
    # follow-up.
    ses_use_fake: bool = True
    ses_from_email: str = "noreply@maihomme.com"
    ses_region: str = "af-south-1"
    ses_endpoint_url: str = ""
    unsubscribe_base_url: str = "https://maihomme.com/notifications/unsubscribe"
    # Server secret for signing the email unsubscribe link (SCRUM-122). The link
    # carries the user id + an HMAC of it so the unauthenticated unsubscribe
    # endpoint can't be used to opt anyone out. MUST be set to a strong random
    # value in every real environment.
    unsubscribe_secret: str = "change-me-to-a-long-random-unsubscribe-secret"
    email_via_celery: bool = False
    email_task_max_retries: int = 5
    email_task_retry_backoff_max_seconds: int = 600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
