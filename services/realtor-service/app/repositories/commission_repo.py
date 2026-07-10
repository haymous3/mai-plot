"""Access to the commissions table (owned by realtor-service, SCRUM-74).

Accrual reads completed transactions + their completed inspection (cross-service,
shared DB) to find deals that owe a commission but don't have one recorded yet.
The commissions row itself is realtor-service's; no escrow_ledger/money movement
happens here (that's M3 / SCRUM-86).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CommissionAccrual:
    """A completed deal that owes a (not-yet-recorded) commission."""

    transaction_id: UUID
    inspection_id: UUID
    realtor_id: UUID
    agreed_price_kobo: int


@dataclass(frozen=True)
class CommissionTotals:
    pending_kobo: int
    available_kobo: int
    withdrawn_kobo: int


@dataclass(frozen=True)
class RealtorCommissionRow:
    """One commission line for the realtor's Earnings transaction history
    (SCRUM-140), joined to its deal's property. amount_kobo is BIGINT kobo."""

    commission_id: UUID
    transaction_id: UUID
    amount_kobo: int
    rate_bps: int
    status: str
    created_at: datetime
    available_at: datetime
    disbursed_at: datetime | None
    property_title: str | None


@dataclass(frozen=True)
class DisbursableCommission:
    """An available commission ready to disburse, with the deal's seller (read
    cross-service) — the payer on the disbursement payment_event."""

    commission_id: UUID
    transaction_id: UUID
    realtor_id: UUID
    seller_id: UUID
    amount_kobo: int


class CommissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_accruable(self, *, limit: int = 500) -> list[CommissionAccrual]:
        """Completed transactions whose inspection is completed and which have no
        commission row yet."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT t.id AS transaction_id, i.id AS inspection_id,
                           i.realtor_id, t.agreed_price_kobo
                    FROM transactions t
                    JOIN inspections i
                        ON i.transaction_id = t.id AND i.status = 'completed'
                    LEFT JOIN commissions c ON c.transaction_id = t.id
                    WHERE t.stage = 'completed' AND c.id IS NULL
                    ORDER BY t.id
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).all()
        return [
            CommissionAccrual(
                transaction_id=r.transaction_id,
                inspection_id=r.inspection_id,
                realtor_id=r.realtor_id,
                agreed_price_kobo=r.agreed_price_kobo,
            )
            for r in rows
        ]

    async def create(
        self,
        *,
        realtor_id: UUID,
        transaction_id: UUID,
        inspection_id: UUID,
        amount_kobo: int,
        rate_bps: int,
        available_at: datetime,
    ) -> bool:
        """Record a pending commission. Idempotent on transaction_id (ON CONFLICT
        DO NOTHING) — returns True only if a new row was inserted."""
        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO commissions
                        (realtor_id, transaction_id, inspection_id, amount_kobo,
                         rate_bps, available_at)
                    VALUES (:realtor, :tx, :insp, :amount, :bps, :available_at)
                    ON CONFLICT (transaction_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "realtor": realtor_id,
                    "tx": transaction_id,
                    "insp": inspection_id,
                    "amount": amount_kobo,
                    "bps": rate_bps,
                    "available_at": available_at,
                },
            )
        ).first()
        return row is not None

    async def release_due(self) -> int:
        """Flip pending -> available for every commission whose hold has elapsed.
        Returns how many were released."""
        rows = (
            await self._session.execute(
                text(
                    "UPDATE commissions SET status = 'available', updated_at = NOW() "
                    "WHERE status = 'pending' AND available_at <= NOW() RETURNING id"
                )
            )
        ).all()
        return len(rows)

    async def list_disbursable(self, *, limit: int = 500) -> list[DisbursableCommission]:
        """Available commissions not yet withdrawn, joined to the deal's seller
        (cross-service read of transactions) — the payer on the payout."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT c.id AS commission_id, c.transaction_id, c.realtor_id,
                           t.seller_id, c.amount_kobo
                    FROM commissions c
                    JOIN transactions t ON t.id = c.transaction_id
                    WHERE c.status = 'available'
                    ORDER BY c.available_at
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).all()
        return [
            DisbursableCommission(
                commission_id=r.commission_id,
                transaction_id=r.transaction_id,
                realtor_id=r.realtor_id,
                seller_id=r.seller_id,
                amount_kobo=r.amount_kobo,
            )
            for r in rows
        ]

    async def completed_disbursement(self, transaction_id: UUID) -> UUID | None:
        """The id of a COMPLETED realtor_commission payment_event for this deal,
        if disbursement finished (cross-service read of payment_events). None
        otherwise — used to reconcile 'available' -> 'withdrawn'."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id FROM payment_events
                    WHERE transaction_id = :tid
                      AND payment_type = 'realtor_commission'
                      AND status = 'completed'
                    LIMIT 1
                    """
                ),
                {"tid": transaction_id},
            )
        ).first()
        return row.id if row is not None else None

    async def mark_withdrawn(self, transaction_id: UUID, *, payment_event_id: UUID) -> bool:
        """Flip an available commission to withdrawn once its payout completed.
        Guarded on status='available' so it's idempotent (a second run is a
        no-op). Returns True only if this call performed the transition."""
        row = (
            await self._session.execute(
                text(
                    """
                    UPDATE commissions
                    SET status = 'withdrawn', payment_event_id = :peid,
                        disbursed_at = NOW(), updated_at = NOW()
                    WHERE transaction_id = :tid AND status = 'available'
                    RETURNING id
                    """
                ),
                {"tid": transaction_id, "peid": payment_event_id},
            )
        ).first()
        return row is not None

    async def list_for_realtor(
        self, realtor_id: UUID, *, limit: int = 100
    ) -> list[RealtorCommissionRow]:
        """The realtor's commission line items, newest first, joined to each
        deal's property — the Earnings transaction history (SCRUM-140)."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT c.id AS commission_id, c.transaction_id, c.amount_kobo,
                           c.rate_bps, c.status, c.created_at, c.available_at,
                           c.disbursed_at, pl.title AS property_title
                    FROM commissions c
                    JOIN transactions t ON t.id = c.transaction_id
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    WHERE c.realtor_id = :rid
                    ORDER BY c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"rid": realtor_id, "limit": limit},
            )
        ).all()
        return [
            RealtorCommissionRow(
                commission_id=r.commission_id,
                transaction_id=r.transaction_id,
                amount_kobo=int(r.amount_kobo),
                rate_bps=r.rate_bps,
                status=r.status,
                created_at=r.created_at,
                available_at=r.available_at,
                disbursed_at=r.disbursed_at,
                property_title=r.property_title,
            )
            for r in rows
        ]

    async def totals_for_realtor(self, realtor_id: UUID) -> CommissionTotals:
        rows = (
            await self._session.execute(
                text(
                    "SELECT status, COALESCE(SUM(amount_kobo), 0) AS total "
                    "FROM commissions WHERE realtor_id = :rid GROUP BY status"
                ),
                {"rid": realtor_id},
            )
        ).all()
        by_status = {r.status: int(r.total) for r in rows}
        return CommissionTotals(
            pending_kobo=by_status.get("pending", 0),
            available_kobo=by_status.get("available", 0),
            withdrawn_kobo=by_status.get("withdrawn", 0),
        )
