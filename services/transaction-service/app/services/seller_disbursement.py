"""Seller disbursement at settlement (SCRUM-85) — §11, moves real money.

For each settled deal (stage='completed', 48h hold elapsed, escrow funded), the
escrow pays out:
  * platform_fee (internal move out of escrow; the figure SCRUM-119 computed) and
  * seller_net = agreed_price − platform_fee − realtor_commission, transferred to
    the seller via Paystack + a PDF receipt.

The realtor commission is RESERVED (subtracted) but disbursed separately by
SCRUM-86 on its own 3-business-day schedule — so the seller (48h) is paid before
the commission leaves escrow. The commission amount must be known: if a realtor
was involved but the commission hasn't accrued yet, the deal waits.

Idempotent + re-entrant (payment_events UNIQUE + status guards); a debit > ₦10M
pends for the existing dual-admin approval. realtor-service's commission row is
read cross-service; this service writes only transaction-service's money tables.
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
from app.repositories.transaction_repo import SettleableDeal, TransactionRepository
from app.services.escrow_ledger import EscrowLedgerService, InsufficientEscrowBalance

logger = logging.getLogger(__name__)

_NS = UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


class SettleOutcome(StrEnum):
    disbursed = "disbursed"
    already_disbursed = "already_disbursed"
    pending_approval = "pending_approval"
    commission_not_ready = "commission_not_ready"
    insufficient_escrow = "insufficient_escrow"


@dataclass(frozen=True)
class SettleResult:
    scanned: int
    disbursed: int
    pending: int
    waiting: int


class SellerDisbursementService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        payments: PaymentEventRepository,
        escrow: EscrowLedgerService,
        receipts: ReceiptStorage,
        transfer_client: PaystackTransferClient,
        audit: AuditLogRepository,
        actor_id: UUID,
        hold_hours: int,
        batch_limit: int = 500,
        provider: str = "paystack",
    ) -> None:
        self._transactions = transactions
        self._payments = payments
        self._escrow = escrow
        self._receipts = receipts
        self._transfer = transfer_client
        self._audit = audit
        self._actor_id = actor_id
        self._hold_hours = hold_hours
        self._batch_limit = batch_limit
        self._provider = provider

    async def run(self) -> SettleResult:
        deals = await self._transactions.list_settleable(
            hold_hours=self._hold_hours, limit=self._batch_limit
        )
        disbursed = pending = waiting = 0
        for deal in deals:
            outcome = await self._settle(deal)
            if outcome == SettleOutcome.disbursed:
                disbursed += 1
            elif outcome == SettleOutcome.pending_approval:
                pending += 1
            elif outcome in (SettleOutcome.commission_not_ready, SettleOutcome.insufficient_escrow):
                waiting += 1
        return SettleResult(
            scanned=len(deals), disbursed=disbursed, pending=pending, waiting=waiting
        )

    async def _settle(self, deal: SettleableDeal) -> SettleOutcome:
        commission = await self._resolve_commission(deal.transaction_id)
        if commission is None:
            return SettleOutcome.commission_not_ready
        seller_net = deal.agreed_price_kobo - deal.platform_fee_kobo - commission
        if seller_net <= 0:
            logger.warning(
                "seller.disburse.non_positive_net",
                extra={"transaction_id": str(deal.transaction_id), "seller_net": seller_net},
            )
            return SettleOutcome.insufficient_escrow

        # 1. Platform fee out of escrow (internal — no external transfer).
        fee_outcome = await self._settle_platform_fee(deal)
        if fee_outcome != SettleOutcome.disbursed:
            return fee_outcome
        # 2. Net proceeds to the seller (Paystack transfer + PDF receipt).
        return await self._settle_seller(deal, seller_net=seller_net, commission=commission)

    async def _resolve_commission(self, transaction_id: UUID) -> int | None:
        """The commission to reserve, or None when a realtor was involved but the
        commission isn't recorded yet (wait for the next sweep)."""
        gate = await self._transactions.commission_gate(transaction_id)
        if gate.amount_kobo is not None:
            return gate.amount_kobo
        if not gate.has_completed_inspection:
            return 0  # no realtor on this deal
        return None  # realtor involved but commission not accrued yet

    async def _settle_platform_fee(self, deal: SettleableDeal) -> SettleOutcome:
        pe = await self._payments.upsert(
            idempotency_key=uuid5(_NS, f"platform_fee:{deal.transaction_id}"),
            payer_id=deal.buyer_id,
            payee_id=None,
            transaction_id=deal.transaction_id,
            amount_kobo=deal.platform_fee_kobo,
            payment_type="platform_fee",
            provider=self._provider,
        )
        if pe.status == "completed":
            return SettleOutcome.disbursed
        effective = await self._ensure_debit(
            deal.transaction_id, pe.id, deal.platform_fee_kobo, "Platform fee"
        )
        if effective is None:
            await self._payments.update_status(pe.id, "failed")
            return SettleOutcome.insufficient_escrow
        if not effective:
            await self._payments.update_status(pe.id, "processing")
            return SettleOutcome.pending_approval
        await self._payments.update_status(pe.id, "completed")
        await self._audit.record(
            actor_id=self._actor_id,
            actor_role="system",
            action="platform_fee.settled",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={"amount_kobo": deal.platform_fee_kobo},
        )
        return SettleOutcome.disbursed

    async def _settle_seller(
        self, deal: SettleableDeal, *, seller_net: int, commission: int
    ) -> SettleOutcome:
        pe = await self._payments.upsert(
            idempotency_key=uuid5(_NS, f"seller_disbursement:{deal.transaction_id}"),
            payer_id=deal.buyer_id,
            payee_id=deal.seller_id,
            transaction_id=deal.transaction_id,
            amount_kobo=seller_net,
            payment_type="seller_disbursement",
            provider=self._provider,
        )
        if pe.status == "completed":
            return SettleOutcome.already_disbursed
        effective = await self._ensure_debit(
            deal.transaction_id, pe.id, seller_net, "Seller proceeds"
        )
        if effective is None:
            await self._payments.update_status(pe.id, "failed")
            return SettleOutcome.insufficient_escrow
        if not effective:
            await self._payments.update_status(pe.id, "processing")
            return SettleOutcome.pending_approval

        transfer = await self._transfer.transfer(
            reference_hint=str(pe.id), amount_kobo=seller_net, recipient_id=deal.seller_id
        )
        await self._payments.update_status(
            pe.id, "completed", provider_reference=transfer.reference
        )
        receipt_key = await self._receipts.write_pdf_receipt(
            pe.id,
            title="Seller disbursement receipt",
            fields={
                "Transaction": str(deal.transaction_id),
                "Agreed price (kobo)": deal.agreed_price_kobo,
                "Platform fee (kobo)": deal.platform_fee_kobo,
                "Realtor commission reserved (kobo)": commission,
                "Net to seller (kobo)": seller_net,
                "Provider reference": transfer.reference,
            },
        )
        await self._audit.record(
            actor_id=self._actor_id,
            actor_role="system",
            action="seller.disbursed",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={
                "amount_kobo": seller_net,
                "provider_reference": transfer.reference,
                "receipt_key": receipt_key,
            },
        )
        logger.info(
            "seller.disbursed",
            extra={"payment_event_id": str(pe.id), "amount_kobo": seller_net},
        )
        return SettleOutcome.disbursed

    async def _ensure_debit(
        self, transaction_id: UUID, payment_event_id: UUID, amount_kobo: int, description: str
    ) -> bool | None:
        """Record the escrow debit if not already there, then report whether it's
        effective. None = the escrow can't cover it (underfunded)."""
        debit = await self._debit_for(transaction_id, payment_event_id)
        if debit is None:
            try:
                await self._escrow.record_debit(
                    transaction_id=transaction_id,
                    amount_kobo=amount_kobo,
                    description=f"{description} {payment_event_id}",
                    payment_event_id=payment_event_id,
                    initiated_by=self._actor_id,
                )
            except InsufficientEscrowBalance:
                return None
            debit = await self._debit_for(transaction_id, payment_event_id)
        return debit is not None and debit.effective

    async def _debit_for(self, transaction_id: UUID, payment_event_id: UUID):  # type: ignore[no-untyped-def]
        entries = await self._escrow.list_entries(transaction_id)
        for entry in entries:
            if entry.entry_type == "debit" and entry.payment_event_id == payment_event_id:
                return entry
        return None
