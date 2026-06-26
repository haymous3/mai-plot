"""Paystack webhook handling (SCRUM-83) — confirms a buyer deposit.

The endpoint is public (Paystack's servers POST it); authenticity is the
HMAC-SHA512 signature over the RAW body, keyed by the Paystack secret. On
`charge.success` for a buyer_deposit we complete the payment_event and record the
escrow CREDIT that funds the deal. Idempotent: a duplicate webhook (Paystack
retries) is a no-op (review.md P4).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.services.escrow_ledger import EscrowLedgerService

logger = logging.getLogger(__name__)


class WebhookOutcome(StrEnum):
    credited = "credited"
    duplicate = "duplicate"
    ignored = "ignored"
    amount_mismatch = "amount_mismatch"


class PaystackWebhookService:
    def __init__(
        self,
        *,
        payments: PaymentEventRepository,
        escrow: EscrowLedgerService,
        audit: AuditLogRepository,
        secret: str,
    ) -> None:
        self._payments = payments
        self._escrow = escrow
        self._audit = audit
        self._secret = secret

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """HMAC-SHA512 of the raw body, constant-time compared to the header."""
        if not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle(self, payload: dict[str, Any]) -> WebhookOutcome:
        if payload.get("event") != "charge.success":
            return WebhookOutcome.ignored

        data = payload.get("data") or {}
        try:
            pe_id = UUID(str(data.get("reference")))
        except (ValueError, TypeError):
            return WebhookOutcome.ignored

        pe = await self._payments.get(pe_id)
        if pe is None or pe.payment_type != "buyer_deposit" or pe.transaction_id is None:
            return WebhookOutcome.ignored
        if pe.status == "completed":
            return WebhookOutcome.duplicate  # idempotent — Paystack retried

        # Trust the server-recorded amount, not the webhook's, but refuse to
        # credit if they disagree (tampering / wrong charge).
        if data.get("amount") != pe.amount_kobo:
            logger.warning(
                "paystack.webhook.amount_mismatch",
                extra={"payment_event_id": str(pe.id)},
            )
            return WebhookOutcome.amount_mismatch

        await self._payments.update_status(
            pe.id, "completed", provider_reference=str(data.get("reference"))
        )
        await self._escrow.record_credit(
            transaction_id=pe.transaction_id,
            amount_kobo=pe.amount_kobo,
            description=f"Buyer deposit {pe.id}",
            payment_event_id=pe.id,
        )
        await self._audit.record(
            actor_id=None,
            actor_role="system",
            action="deposit.completed",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={"transaction_id": str(pe.transaction_id), "amount_kobo": pe.amount_kobo},
        )
        logger.info("paystack.deposit.credited", extra={"payment_event_id": str(pe.id)})
        return WebhookOutcome.credited
