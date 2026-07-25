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

    # Platform fee charged at deal close (SCRUM-119), in basis points
    # (250 = 2.5%). CLAUDE.md fixes the realtor commission at 2% (rule §7) but
    # never set Maiplot's own fee; this is admin/env tunable. The actual money
    # movement (net disbursement to the seller) is M3 / SCRUM-85.
    platform_fee_bps: int = 250

    # Escrow admin endpoints require admin JWT AND an IP whitelist (CLAUDE.md).
    # Kong enforces the allowlist at the edge; this app-level check is defence
    # in depth. Comma-separated IPs; empty = allow any (dev/test default).
    admin_ip_allowlist: str = ""

    # Cross-service notifications (SCRUM-117). When a buyer makes an offer, the
    # seller is alerted by enqueuing the notification-service `notifications.dispatch`
    # Celery task on the shared broker (CLAUDE.md §3: async work via Celery). The
    # send is best-effort — a broker hiccup never blocks or rolls back the offer.
    # notifications_enabled=false (the test/dev default) wires a no-op notifier so
    # no broker is needed; production sets it true + the broker URL.
    notifications_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Realtor commission disbursement (SCRUM-86). §11 — moves real money out of
    # escrow. The escrow debit is initiated by a system actor (this user id must
    # exist in `users`; seeded at deploy). A debit STRICTLY ABOVE ₦10M still
    # escalates to dual admin approval via the existing escrow flow.
    disbursement_actor_id: str = "00000000-0000-0000-0000-000000000001"

    # Paystack rail (charge/collection + payout). paystack_enabled=false wires the
    # FAKE clients (synthetic URLs/references, no network) so deposit + disbursement
    # run end-to-end in dev/CI. Production sets it true + the keys.
    paystack_enabled: bool = False
    paystack_secret_key: str = ""
    paystack_base_url: str = "https://api.paystack.co"
    # Where Paystack redirects the buyer after checkout (frontend route). Optional.
    paystack_callback_url: str = ""
    # Webhook HMAC-SHA512 secret (Paystack signs with your secret key). The
    # /webhooks/paystack handler rejects any body whose signature doesn't match.
    paystack_webhook_secret: str = "change-me-paystack-webhook-secret"

    # Seller disbursement (SCRUM-85). §11 — at settlement the escrow pays out
    # platform_fee + seller_net (= agreed_price − platform_fee − realtor_commission)
    # + (separately) the realtor commission. A beat sweeps deals that reached
    # 'completed' at least seller_disbursement_hold_hours ago.
    seller_disbursement_hold_hours: int = 48
    seller_disbursement_beat_interval_seconds: float = 3600.0  # hourly

    # Failed-payout escrow reversal sweep (SCRUM-147). §11 — reverses the standing
    # escrow debit of a payout whose Paystack transfer failed. Idempotent.
    payout_reconciliation_beat_interval_seconds: float = 3600.0  # hourly

    # Lapsed 72h listing-lock sweep (SCRUM-149). Proactively cancels deals still
    # parked at 'offer_accepted' past their lock window and reopens the listing
    # (the off-request counterpart to OfferService's lazy release). Idempotent.
    lock_sweep_beat_interval_seconds: float = 900.0  # every 15 minutes

    # Lapsed-offer sweep (SCRUM-118). Proactively stamps status='expired' on
    # pending/countered offers past their 72h window (the off-request counterpart
    # to OfferService's lazy expiry), so offer lists reflect reality. Idempotent.
    offer_expiry_sweep_beat_interval_seconds: float = 900.0  # every 15 minutes

    # Payment receipts → PRIVATE S3 (never public). In-memory fake by default so
    # local/CI never reach S3; production sets receipts_storage_use_fake=false.
    receipts_storage_use_fake: bool = True
    receipts_s3_bucket: str = "maiplot-receipts-local"
    receipts_s3_region: str = "af-south-1"
    receipts_s3_endpoint_url: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
