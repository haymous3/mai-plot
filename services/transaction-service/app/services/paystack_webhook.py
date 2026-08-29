"""Paystack webhook handling (SCRUM-83 deposit; SCRUM-145 payout) — §11.

The endpoint is public (Paystack's servers POST it); authenticity is the
HMAC-SHA512 signature over the RAW body, keyed by the Paystack secret. Two event
families are handled:

  * `charge.success` (inbound) — completes a buyer_deposit payment_event and
    records the escrow CREDIT that funds the deal (SCRUM-83).
  * `transfer.success` / `transfer.failed` (outbound) — finalise a payout
    payment_event that a disbursement left `processing` after an async Paystack
    transfer (SCRUM-145 PR2): success -> completed + immutable receipt; failed ->
    failed (the escrow debit already recorded stays put; its reversal is the
    reconciliation sweep's job, backlog).

Everything is idempotent: a duplicate webhook (Paystack retries) is a no-op, and
a late event that can't legally change the current state is ignored — never a flip
that resurrects a failed payout or un-settles a completed one (review.md P4).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.adapters.receipt_storage import ReceiptStorage
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.payment_repo import PaymentEventDetail, PaymentEventRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.seller_notifier import SellerNotifier

logger = logging.getLogger(__name__)

# Outbound payout payment_types a transfer webhook may finalise.
_PAYOUT_TYPES = frozenset({"realtor_commission", "seller_disbursement"})


class WebhookOutcome(StrEnum):
    credited = "credited"
    duplicate = "duplicate"
    ignored = "ignored"
    amount_mismatch = "amount_mismatch"
    # Payout (transfer) outcomes.
    settled = "settled"
    failed = "failed"


class PaystackWebhookService:
    def __init__(
        self,
        *,
        payments: PaymentEventRepository,
        escrow: EscrowLedgerService,
        receipts: ReceiptStorage,
        audit: AuditLogRepository,
        secret: str,
        transactions: TransactionRepository | None = None,
        sellers: SellerNotifier | None = None,
    ) -> None:
        self._payments = payments
        self._escrow = escrow
        self._receipts = receipts
        self._audit = audit
        self._secret = secret
        # SCRUM-195. Optional so every existing construction of this service —
        # including the tests that predate the notification — keeps working and
        # simply sends nothing.
        self._transactions = transactions
        self._sellers = sellers

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """HMAC-SHA512 of the raw body, constant-time compared to the header."""
        if not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle(self, payload: dict[str, Any]) -> WebhookOutcome:
        event = payload.get("event")
        if event == "charge.success":
            return await self._handle_charge(payload)
        if event in ("transfer.success", "transfer.failed"):
            return await self._handle_transfer(event, payload)
        return WebhookOutcome.ignored

    async def _handle_charge(self, payload: dict[str, Any]) -> WebhookOutcome:
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

        # Tell the seller their escrow has been funded (SCRUM-195). LAST, and
        # best-effort: the credit above is the money and is already committed,
        # so a broker outage must not turn a successful deposit into a webhook
        # error that Paystack then retries.
        #
        # Only `deposit_confirmed` is raised, never a "deposit received" at
        # initiation. At initiation the buyer has only been handed a Paystack
        # authorization URL — no money has moved — so telling a seller a
        # deposit had been made would be false. The design shows both states;
        # only one of them is real here.
        await self._notify_seller(pe.transaction_id, pe.amount_kobo)
        return WebhookOutcome.credited

    async def _notify_seller(self, transaction_id: UUID, amount_kobo: int) -> None:
        if self._transactions is None or self._sellers is None:
            return
        try:
            status = await self._transactions.get_status(transaction_id)
            if status is None:
                return
            await self._sellers.deposit_confirmed(
                seller_id=status.seller_id,
                transaction_id=transaction_id,
                amount_kobo=amount_kobo,
            )
        except Exception as exc:  # never let a message failure fail the webhook
            logger.warning(
                "paystack.deposit.notify_failed",
                extra={"transaction_id": str(transaction_id), "error": str(exc)},
            )

    async def _handle_transfer(self, event: str, payload: dict[str, Any]) -> WebhookOutcome:
        """Finalise a payout the disbursement left `processing`. We look the event
        up by the reference WE set on the transfer (the payment_event id), never by
        Paystack's transfer_code, so a payout is matched even if the webhook lands
        before the disbursement stamped the transfer_code."""
        data = payload.get("data") or {}
        try:
            pe_id = UUID(str(data.get("reference")))
        except (ValueError, TypeError):
            return WebhookOutcome.ignored

        pe = await self._payments.get(pe_id)
        if pe is None or pe.payment_type not in _PAYOUT_TYPES:
            return WebhookOutcome.ignored

        reference = str(data.get("transfer_code") or pe.id)
        if event == "transfer.success":
            return await self._settle_transfer(pe, reference)
        return await self._fail_transfer(pe, reference)

    async def _settle_transfer(self, pe: PaymentEventDetail, reference: str) -> WebhookOutcome:
        if pe.status == "completed":
            return WebhookOutcome.duplicate  # Paystack retried a delivered success
        if pe.status != "processing":
            # Only an in-flight payout can be settled by a webhook; anything else
            # (initiated / failed) is unexpected — never resurrect it.
            logger.warning(
                "paystack.transfer.success_unexpected_state",
                extra={"payment_event_id": str(pe.id), "status": pe.status},
            )
            return WebhookOutcome.ignored

        await self._payments.update_status(pe.id, "completed", provider_reference=reference)
        receipt_key = await self._receipts.write_receipt(
            pe.id,
            {
                "payment_event_id": str(pe.id),
                "payment_type": pe.payment_type,
                "transaction_id": str(pe.transaction_id) if pe.transaction_id else None,
                "amount_kobo": pe.amount_kobo,
                "provider": "paystack",
                "provider_reference": reference,
                "settled_via": "transfer_webhook",
            },
        )
        await self._audit.record(
            actor_id=None,
            actor_role="system",
            action="transfer.settled",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={
                "payment_type": pe.payment_type,
                "amount_kobo": pe.amount_kobo,
                "provider_reference": reference,
                "receipt_key": receipt_key,
            },
        )
        logger.info("paystack.transfer.settled", extra={"payment_event_id": str(pe.id)})
        return WebhookOutcome.settled

    async def _fail_transfer(self, pe: PaymentEventDetail, reference: str) -> WebhookOutcome:
        if pe.status == "failed":
            return WebhookOutcome.duplicate  # Paystack retried a delivered failure
        if pe.status == "completed":
            # A settled payout can't be un-settled by a late failure event.
            logger.warning(
                "paystack.transfer.failed_after_completed",
                extra={"payment_event_id": str(pe.id)},
            )
            return WebhookOutcome.ignored

        await self._payments.update_status(pe.id, "failed", provider_reference=reference)
        await self._audit.record(
            actor_id=None,
            actor_role="system",
            action="transfer.failed",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={"payment_type": pe.payment_type, "provider_reference": reference},
        )
        # The escrow debit recorded at disbursement time stays put — its reversal
        # is the reconciliation sweep's job (backlog), not the webhook's.
        logger.warning(
            "paystack.transfer.failed",
            extra={"payment_event_id": str(pe.id), "escrow_debit": "awaits_reconciliation"},
        )
        return WebhookOutcome.failed
