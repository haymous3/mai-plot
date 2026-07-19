"""Append-only access to escrow_ledger (SCRUM-69).

A single-account ledger for the escrow funds of one transaction: `credit` =
money into escrow (buyer payment), `debit` = money out (disbursement, fee,
commission, refund). The balance is Σcredit − Σdebit over *effective* entries;
it nets to zero once a deal is fully disbursed.

Append-only: this repository only INSERTs and reads. The single exception is
`set_second_approval`, which fills the dual-approval columns exactly once
(NULL → value) — it never touches an entry's financial fields (entry_type,
amount_kobo, transaction_id, payment_event_id). A DB trigger enforcing this at
the row level is a deferred follow-up (transaction_events uses the same
service-layer convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class LedgerEntryRow:
    id: UUID
    transaction_id: UUID
    entry_type: str
    amount_kobo: int
    description: str
    payment_event_id: UUID | None
    requires_dual_approval: bool
    approved_by_1: UUID | None
    approved_by_2: UUID | None
    approved_at: datetime | None
    created_at: datetime

    @property
    def effective(self) -> bool:
        """An entry counts toward the balance unless it is a dual-approval debit
        still awaiting its second approval."""
        return not self.requires_dual_approval or self.approved_by_2 is not None


@dataclass(frozen=True)
class EscrowBalance:
    transaction_id: UUID
    balance_kobo: int
    pending_kobo: int


@dataclass(frozen=True)
class PendingApproval:
    entry_id: UUID
    approved_by_1: UUID | None
    amount_kobo: int


@dataclass(frozen=True)
class FailedPayout:
    """A failed payout whose escrow debit is still standing and unreversed."""

    payment_event_id: UUID
    transaction_id: UUID
    debit_kobo: int


class EscrowLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_entry(
        self,
        *,
        transaction_id: UUID,
        entry_type: str,
        amount_kobo: int,
        description: str,
        payment_event_id: UUID,
        requires_dual_approval: bool,
        approved_by_1: UUID | None,
    ) -> UUID:
        """Append a single ledger row and return its id. Money fields are never
        mutated after this insert."""
        entry_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO escrow_ledger
                        (transaction_id, entry_type, amount_kobo, description,
                         payment_event_id, requires_dual_approval, approved_by_1)
                    VALUES
                        (:tid, :etype, :amount, :descr, :peid, :dual, :by1)
                    RETURNING id
                    """
                ),
                {
                    "tid": transaction_id,
                    "etype": entry_type,
                    "amount": amount_kobo,
                    "descr": description,
                    "peid": payment_event_id,
                    "dual": requires_dual_approval,
                    "by1": approved_by_1,
                },
            )
        ).scalar_one()
        assert isinstance(entry_id, UUID)
        return entry_id

    async def balance(self, transaction_id: UUID) -> EscrowBalance:
        """Σcredit − Σdebit over effective entries (credits are always
        effective; a dual-approval debit counts only once approved_by_2 is set).
        `pending` is the sum of debits still awaiting a second approval."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                      COALESCE(SUM(CASE
                        WHEN entry_type = 'credit' THEN amount_kobo
                        WHEN entry_type = 'debit'
                             AND (NOT requires_dual_approval OR approved_by_2 IS NOT NULL)
                          THEN -amount_kobo
                        ELSE 0 END), 0) AS balance,
                      COALESCE(SUM(CASE
                        WHEN entry_type = 'debit'
                             AND requires_dual_approval AND approved_by_2 IS NULL
                          THEN amount_kobo
                        ELSE 0 END), 0) AS pending
                    FROM escrow_ledger
                    WHERE transaction_id = :tid
                    """
                ),
                {"tid": transaction_id},
            )
        ).one()
        return EscrowBalance(
            transaction_id=transaction_id,
            balance_kobo=int(row.balance),
            pending_kobo=int(row.pending),
        )

    async def list_for_transaction(self, transaction_id: UUID) -> list[LedgerEntryRow]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, transaction_id, entry_type, amount_kobo, description,
                           payment_event_id, requires_dual_approval,
                           approved_by_1, approved_by_2, approved_at, created_at
                    FROM escrow_ledger
                    WHERE transaction_id = :tid
                    ORDER BY created_at
                    """
                ),
                {"tid": transaction_id},
            )
        ).all()
        return [
            LedgerEntryRow(
                id=r.id,
                transaction_id=r.transaction_id,
                entry_type=r.entry_type,
                amount_kobo=r.amount_kobo,
                description=r.description,
                payment_event_id=r.payment_event_id,
                requires_dual_approval=r.requires_dual_approval,
                approved_by_1=r.approved_by_1,
                approved_by_2=r.approved_by_2,
                approved_at=r.approved_at,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def pending_approvals_for_payment_event(
        self, payment_event_id: UUID
    ) -> list[PendingApproval]:
        """Dual-approval debits for a payment_event still awaiting approval #2."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, approved_by_1, amount_kobo
                    FROM escrow_ledger
                    WHERE payment_event_id = :peid
                      AND requires_dual_approval AND approved_by_2 IS NULL
                    """
                ),
                {"peid": payment_event_id},
            )
        ).all()
        return [
            PendingApproval(entry_id=r.id, approved_by_1=r.approved_by_1, amount_kobo=r.amount_kobo)
            for r in rows
        ]

    async def list_failed_payouts_needing_reversal(
        self, *, payout_types: tuple[str, ...], limit: int = 500
    ) -> list[FailedPayout]:
        """Failed payout payment_events whose escrow DEBIT is still effective and
        has no compensating reversal credit yet (SCRUM-147). The debit total per
        event is what a reversal must credit back. Ordering is oldest-first so a
        long backlog drains deterministically.

        A payout event's only ledger entry is its debit, so a `credit` linked to
        the same payment_event_id can only be a prior reversal — that NOT EXISTS
        is the idempotency guard the sweep relies on."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT pe.id AS payment_event_id,
                           pe.transaction_id AS transaction_id,
                           SUM(led.amount_kobo) AS debit_kobo
                    FROM payment_events pe
                    JOIN escrow_ledger led
                      ON led.payment_event_id = pe.id
                     AND led.entry_type = 'debit'
                     AND (NOT led.requires_dual_approval OR led.approved_by_2 IS NOT NULL)
                    WHERE pe.status = 'failed'
                      AND pe.payment_type = ANY(:ptypes)
                      AND pe.transaction_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM escrow_ledger rev
                        WHERE rev.payment_event_id = pe.id AND rev.entry_type = 'credit'
                      )
                    GROUP BY pe.id, pe.transaction_id
                    ORDER BY MIN(led.created_at)
                    LIMIT :limit
                    """
                ),
                {"ptypes": list(payout_types), "limit": limit},
            )
        ).all()
        return [
            FailedPayout(
                payment_event_id=r.payment_event_id,
                transaction_id=r.transaction_id,
                debit_kobo=int(r.debit_kobo),
            )
            for r in rows
        ]

    async def set_second_approval(self, entry_id: UUID, *, approver: UUID) -> bool:
        """Record the second approval on a pending entry (the only post-insert
        write, NULL → value). Guarded on approved_by_2 IS NULL so a concurrent
        approval cannot overwrite the first; returns False if it was already
        approved."""
        row = (
            await self._session.execute(
                text(
                    """
                    UPDATE escrow_ledger
                    SET approved_by_2 = :approver, approved_at = NOW()
                    WHERE id = :id AND approved_by_2 IS NULL
                    RETURNING id
                    """
                ),
                {"approver": approver, "id": entry_id},
            )
        ).first()
        return row is not None
