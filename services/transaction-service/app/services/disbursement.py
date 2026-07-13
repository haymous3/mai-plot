"""Realtor commission disbursement (SCRUM-86) — §11, moves real money.

Orchestrates one commission payout, idempotently and re-entrantly:

  1. upsert a `realtor_commission` payment_event (the idempotency anchor) — a
     duplicate run reuses the same event and never double-pays;
  2. record an escrow DEBIT via EscrowLedgerService (which enforces the
     dual-approval gate STRICTLY ABOVE ₦10M and rejects an underfunded escrow);
  3. if the debit is still pending a second admin approval, stop (a later run
     completes it once approved);
  4. otherwise place the (faked) Paystack transfer, mark the event completed,
     write an immutable receipt, and audit.

The matching `commissions.status` -> 'withdrawn' flip is realtor-service's
(SCRUM-86 PR-B), reconciled from the completed payment_event — this service only
writes transaction-service's own money tables.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from app.adapters.paystack import PaystackTransferClient
from app.adapters.receipt_storage import ReceiptStorage
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.repositories.payout_account_repo import PayoutAccountRepository
from app.services.escrow_ledger import EscrowLedgerService, InsufficientEscrowBalance

logger = logging.getLogger(__name__)

# Stable namespace so the idempotency key is deterministic per (commission) deal.
_IDEMPOTENCY_NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")
_PAYMENT_TYPE = "realtor_commission"


class DisburseOutcome(StrEnum):
    disbursed = "disbursed"
    already_disbursed = "already_disbursed"
    pending_approval = "pending_approval"
    insufficient_escrow = "insufficient_escrow"
    # The payee hasn't registered a payout account yet — nothing is debited; a
    # later sweep retries once they do (SCRUM-145).
    no_payout_account = "no_payout_account"
    # A real (async) transfer was accepted and is in flight; the transfer webhook
    # will complete the payment_event (SCRUM-145 PR3).
    processing = "processing"
    # Paystack rejected the transfer outright (rare — usually it goes pending).
    transfer_failed = "transfer_failed"


@dataclass(frozen=True)
class DisburseRequest:
    commission_id: UUID
    transaction_id: UUID
    realtor_id: UUID
    seller_id: UUID
    amount_kobo: int


@dataclass(frozen=True)
class DisburseResult:
    outcome: DisburseOutcome
    payment_event_id: UUID


class CommissionDisbursementService:
    def __init__(
        self,
        *,
        payments: PaymentEventRepository,
        escrow: EscrowLedgerService,
        receipts: ReceiptStorage,
        transfer_client: PaystackTransferClient,
        payout_accounts: PayoutAccountRepository,
        audit: AuditLogRepository,
        actor_id: UUID,
        provider: str = "paystack",
    ) -> None:
        self._payments = payments
        self._escrow = escrow
        self._receipts = receipts
        self._transfer = transfer_client
        self._payout_accounts = payout_accounts
        self._audit = audit
        self._actor_id = actor_id
        self._provider = provider

    @staticmethod
    def _idempotency_key(transaction_id: UUID) -> UUID:
        return uuid5(_IDEMPOTENCY_NAMESPACE, f"{_PAYMENT_TYPE}:{transaction_id}")

    async def disburse(self, req: DisburseRequest) -> DisburseResult:
        pe = await self._payments.upsert(
            idempotency_key=self._idempotency_key(req.transaction_id),
            payer_id=req.seller_id,
            payee_id=req.realtor_id,
            transaction_id=req.transaction_id,
            amount_kobo=req.amount_kobo,
            payment_type=_PAYMENT_TYPE,
            provider=self._provider,
        )
        if pe.status == "completed":
            return DisburseResult(DisburseOutcome.already_disbursed, pe.id)

        # Resolve the realtor's payout destination BEFORE touching escrow — never
        # debit money we have nowhere to send. No account yet -> retry next sweep.
        recipient_code = await self._recipient_code(req.realtor_id)
        if recipient_code is None:
            logger.info(
                "commission.disburse.no_payout_account",
                extra={"payment_event_id": str(pe.id), "realtor_id": str(req.realtor_id)},
            )
            return DisburseResult(DisburseOutcome.no_payout_account, pe.id)

        debit = await self._debit_for(req.transaction_id, pe.id)
        if debit is None:
            try:
                await self._escrow.record_debit(
                    transaction_id=req.transaction_id,
                    amount_kobo=req.amount_kobo,
                    description=f"Realtor commission {req.commission_id}",
                    payment_event_id=pe.id,
                    initiated_by=self._actor_id,
                )
            except InsufficientEscrowBalance:
                await self._payments.update_status(pe.id, "failed")
                logger.warning(
                    "commission.disburse.insufficient_escrow",
                    extra={
                        "payment_event_id": str(pe.id),
                        "transaction_id": str(req.transaction_id),
                    },
                )
                return DisburseResult(DisburseOutcome.insufficient_escrow, pe.id)
            debit = await self._debit_for(req.transaction_id, pe.id)

        if debit is None or not debit.effective:
            # Large payout (>₦10M) awaiting a second admin approval — a later run
            # completes the transfer once it's approved.
            await self._payments.update_status(pe.id, "processing")
            return DisburseResult(DisburseOutcome.pending_approval, pe.id)

        transfer = await self._transfer.transfer(
            reference_hint=str(pe.id), amount_kobo=req.amount_kobo, recipient_code=recipient_code
        )
        if transfer.status == "pending":
            # Real async transfer accepted; the transfer webhook (PR3) completes
            # the event + writes the receipt once Paystack confirms settlement.
            await self._payments.update_status(
                pe.id, "processing", provider_reference=transfer.reference
            )
            logger.info(
                "commission.disburse.processing",
                extra={"payment_event_id": str(pe.id), "provider_reference": transfer.reference},
            )
            return DisburseResult(DisburseOutcome.processing, pe.id)
        if transfer.status == "failed":
            await self._payments.update_status(
                pe.id, "failed", provider_reference=transfer.reference
            )
            logger.warning(
                "commission.disburse.transfer_failed", extra={"payment_event_id": str(pe.id)}
            )
            return DisburseResult(DisburseOutcome.transfer_failed, pe.id)

        # Synchronous settle (the fake, or a Paystack transfer that returns
        # 'success' immediately).
        await self._payments.update_status(
            pe.id, "completed", provider_reference=transfer.reference
        )
        receipt_key = await self._receipts.write_receipt(
            pe.id,
            {
                "payment_event_id": str(pe.id),
                "commission_id": str(req.commission_id),
                "transaction_id": str(req.transaction_id),
                "realtor_id": str(req.realtor_id),
                "amount_kobo": req.amount_kobo,
                "provider": self._provider,
                "provider_reference": transfer.reference,
            },
        )
        await self._audit.record(
            actor_id=self._actor_id,
            actor_role="system",
            action="commission.disbursed",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={
                "amount_kobo": req.amount_kobo,
                "provider_reference": transfer.reference,
                "receipt_key": receipt_key,
            },
        )
        logger.info(
            "commission.disbursed",
            extra={"payment_event_id": str(pe.id), "amount_kobo": req.amount_kobo},
        )
        return DisburseResult(DisburseOutcome.disbursed, pe.id)

    async def _recipient_code(self, payee_id: UUID) -> str | None:
        account = await self._payout_accounts.get(payee_id)
        return account.recipient_code if account is not None else None

    async def _debit_for(self, transaction_id: UUID, payment_event_id: UUID):  # type: ignore[no-untyped-def]
        entries = await self._escrow.list_entries(transaction_id)
        for entry in entries:
            if entry.entry_type == "debit" and entry.payment_event_id == payment_event_id:
                return entry
        return None
