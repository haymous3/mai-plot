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
