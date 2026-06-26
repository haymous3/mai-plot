"""Loan disbursement → escrow credit (SCRUM-128) — §11, moves real money IN.

When a bank confirms it has disbursed an approved loan, those funds land in the
deal's escrow alongside the buyer's (reduced) deposit. loan-service enqueues the
`payments.credit_loan_disbursement` task that calls this; the money write lives
here because transaction-service is the sole owner of the escrow ledger.

Idempotent + re-entrant, like CommissionDisbursementService (SCRUM-86):

  1. upsert a `loan_disbursement` payment_event keyed by the loan — a duplicate
     webhook reuses the same event and can never double-credit;
  2. if a credit for that event already exists (a crash between credit and the
     status flip), don't credit again — just finish;
  3. otherwise record the escrow CREDIT (credits never require dual approval —
     they only increase what escrow holds), mark the event completed, and audit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.services.escrow_ledger import EscrowLedgerService

logger = logging.getLogger(__name__)

# Stable namespace so the idempotency key is deterministic per loan.
_IDEMPOTENCY_NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")
_PAYMENT_TYPE = "loan_disbursement"


class CreditOutcome(StrEnum):
    credited = "credited"
    already_credited = "already_credited"


@dataclass(frozen=True)
class CreditRequest:
    loan_id: UUID
    transaction_id: UUID
    buyer_id: UUID
    amount_kobo: int


@dataclass(frozen=True)
class CreditResult:
    outcome: CreditOutcome
    payment_event_id: UUID


class LoanDisbursementCreditService:
    def __init__(
        self,
        *,
        payments: PaymentEventRepository,
        escrow: EscrowLedgerService,
        audit: AuditLogRepository,
        actor_id: UUID,
        provider: str = "bank_transfer",
    ) -> None:
        self._payments = payments
        self._escrow = escrow
        self._audit = audit
        self._actor_id = actor_id
        self._provider = provider

    @staticmethod
    def _idempotency_key(loan_id: UUID) -> UUID:
        return uuid5(_IDEMPOTENCY_NAMESPACE, f"{_PAYMENT_TYPE}:{loan_id}")

    async def credit(self, req: CreditRequest) -> CreditResult:
        # payer_id = buyer: the loan is the buyer's debt funding their escrow side
        # (the same party that funds the deposit). payee_id is None — funds enter
        # the single escrow account, not a specific recipient.
        pe = await self._payments.upsert(
            idempotency_key=self._idempotency_key(req.loan_id),
            payer_id=req.buyer_id,
            payee_id=None,
            transaction_id=req.transaction_id,
            amount_kobo=req.amount_kobo,
            payment_type=_PAYMENT_TYPE,
            provider=self._provider,
        )
        if pe.status == "completed":
            return CreditResult(CreditOutcome.already_credited, pe.id)

        if not await self._credit_exists(req.transaction_id, pe.id):
            await self._escrow.record_credit(
                transaction_id=req.transaction_id,
                amount_kobo=req.amount_kobo,
                description=f"Loan disbursement {req.loan_id}",
                payment_event_id=pe.id,
                recorded_by=self._actor_id,
            )

        await self._payments.update_status(pe.id, "completed")
        await self._audit.record(
            actor_id=self._actor_id,
            actor_role="system",
            action="loan.disbursement_credited",
            entity_type="payment_event",
            entity_id=pe.id,
            new_value={
                "loan_id": str(req.loan_id),
                "transaction_id": str(req.transaction_id),
                "amount_kobo": req.amount_kobo,
            },
        )
        logger.info(
            "loan.disbursement_credited",
            extra={"payment_event_id": str(pe.id), "amount_kobo": req.amount_kobo},
        )
        return CreditResult(CreditOutcome.credited, pe.id)

    async def _credit_exists(self, transaction_id: UUID, payment_event_id: UUID) -> bool:
        entries = await self._escrow.list_entries(transaction_id)
        return any(
            e.entry_type == "credit" and e.payment_event_id == payment_event_id for e in entries
        )
