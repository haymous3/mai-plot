"""Escrow ledger orchestration (SCRUM-69).

Records escrow credits/debits as double-entry bookkeeping on a single-account
ledger, enforces the dual-approval gate on large disbursements (CLAUDE.md rule
§9 — escrow moves above ₦10,000,000), and exposes the running balance. Every
mutation is also written to audit_log.

This is the seam the payment flow (M3, Paystack) calls — it does NOT move money
itself. Each entry is linked to an existing payment_event.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowBalance, EscrowLedgerRepository, LedgerEntryRow

logger = logging.getLogger(__name__)

# CLAUDE.md rule §9 — an escrow movement STRICTLY ABOVE ₦10,000,000
# (1,000,000,000 kobo) requires two distinct admin approvals.
DUAL_APPROVAL_THRESHOLD_KOBO = 1_000_000_000


class EscrowError(RuntimeError):
    pass


class InsufficientEscrowBalance(EscrowError):
    """A debit would disburse more than the effective escrow balance holds."""


class NoPendingApproval(EscrowError):
    """No dual-approval debit is awaiting a second approval for this payment."""


class SameApprover(EscrowError):
    """The second approval must come from a different admin than the first."""


class EscrowLedgerService:
    def __init__(
        self,
        *,
        ledger: EscrowLedgerRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._ledger = ledger
        self._audit = audit

    async def record_credit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        recorded_by: UUID | None = None,
    ) -> UUID:
        """Funds INTO escrow (e.g. a buyer payment). Credits never require dual
        approval — they increase what escrow holds."""
        entry_id = await self._ledger.record_entry(
            transaction_id=transaction_id,
            entry_type="credit",
            amount_kobo=amount_kobo,
            description=description,
            payment_event_id=payment_event_id,
            requires_dual_approval=False,
            approved_by_1=recorded_by,
        )
        await self._audit.record(
            actor_id=recorded_by,
            actor_role="system" if recorded_by is None else "admin",
            action="escrow.credit",
            entity_type="escrow_ledger",
            entity_id=entry_id,
            new_value={"transaction_id": str(transaction_id), "amount_kobo": amount_kobo},
        )
        logger.info(
            "escrow.credit",
            extra={"transaction_id": str(transaction_id), "amount_kobo": amount_kobo},
        )
        return entry_id

    async def record_debit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        initiated_by: UUID,
    ) -> UUID:
        """Funds OUT of escrow (disbursement / fee / commission / refund),
        initiated by an admin. A debit may not exceed the effective balance.
        Above the threshold it is recorded as PENDING a second approval and does
        not reduce the balance until approval #2 lands."""
        balance = await self._ledger.balance(transaction_id)
        if amount_kobo > balance.balance_kobo:
            raise InsufficientEscrowBalance()

        requires_dual = amount_kobo > DUAL_APPROVAL_THRESHOLD_KOBO
        entry_id = await self._ledger.record_entry(
            transaction_id=transaction_id,
            entry_type="debit",
            amount_kobo=amount_kobo,
            description=description,
            payment_event_id=payment_event_id,
            requires_dual_approval=requires_dual,
            approved_by_1=initiated_by,
        )
        await self._audit.record(
            actor_id=initiated_by,
            actor_role="admin",
            action="escrow.debit_pending" if requires_dual else "escrow.debit",
            entity_type="escrow_ledger",
            entity_id=entry_id,
            new_value={
                "transaction_id": str(transaction_id),
                "amount_kobo": amount_kobo,
                "requires_dual_approval": requires_dual,
            },
        )
        logger.info(
            "escrow.debit",
            extra={
                "transaction_id": str(transaction_id),
                "amount_kobo": amount_kobo,
                "requires_dual_approval": requires_dual,
            },
        )
        return entry_id

    async def second_approval(
        self,
        *,
        payment_event_id: UUID,
        approver: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> list[UUID]:
        """Apply the second admin approval to the pending dual-approval debit(s)
        for a payment_event. The approver must differ from the first approver."""
        pending = await self._ledger.pending_approvals_for_payment_event(payment_event_id)
        if not pending:
            raise NoPendingApproval()
        if any(p.approved_by_1 == approver for p in pending):
            raise SameApprover()

        approved: list[UUID] = []
        for p in pending:
            if await self._ledger.set_second_approval(p.entry_id, approver=approver):
                approved.append(p.entry_id)
                await self._audit.record(
                    actor_id=approver,
                    actor_role="admin",
                    action="escrow.approved",
                    entity_type="escrow_ledger",
                    entity_id=p.entry_id,
                    old_value={"approved_by_2": None},
                    new_value={"approved_by_2": str(approver)},
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        if not approved:  # a concurrent approval beat us to all of them
            raise NoPendingApproval()
        logger.info(
            "escrow.second_approval",
            extra={"payment_event_id": str(payment_event_id), "entries": len(approved)},
        )
        return approved

    async def balance(self, transaction_id: UUID) -> EscrowBalance:
        return await self._ledger.balance(transaction_id)

    async def list_entries(self, transaction_id: UUID) -> list[LedgerEntryRow]:
        return await self._ledger.list_for_transaction(transaction_id)
