"""Read-only wallet queries for the buyer "My Wallet" surface (SCRUM-95).

All aggregates are derived from existing tables (escrow_ledger, payment_events,
transactions) scoped to the buyer — no wallet-balance primitive, no writes.
Amounts are BIGINT kobo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Deals that no longer hold value / aren't "active properties".
_TERMINAL = ("cancelled", "loan_rejected")


@dataclass(frozen=True)
class WalletTotals:
    in_escrow_kobo: int
    escrow_deal_count: int
    total_invested_kobo: int
    active_property_count: int


@dataclass(frozen=True)
class ActivePaymentRow:
    transaction_id: UUID
    listing_id: UUID
    property_title: str | None
    paid_kobo: int
    total_kobo: int
    stage: str


@dataclass(frozen=True)
class PaymentRow:
    id: UUID
    payment_type: str
    amount_kobo: int
    status: str
    provider: str
    provider_reference: str | None
    transaction_id: UUID | None
    property_title: str | None
    created_at: datetime


class WalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def totals(self, buyer_id: UUID) -> WalletTotals:
        # In escrow: net (credit − debit) per deal, summed over deals still holding
        # a positive balance. escrow_deal_count is how many of those.
        escrow = (
            await self._session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(net), 0) AS in_escrow, COUNT(*) AS deals
                    FROM (
                        SELECT COALESCE(SUM(
                            CASE e.entry_type WHEN 'credit' THEN e.amount_kobo
                                              ELSE -e.amount_kobo END), 0) AS net
                        FROM transactions t
                        JOIN escrow_ledger e ON e.transaction_id = t.id
                        WHERE t.buyer_id = :buyer_id
                        GROUP BY t.id
                    ) per_deal
                    WHERE net > 0
                    """
                ),
                {"buyer_id": buyer_id},
            )
        ).first()

        invested = (
            await self._session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(amount_kobo), 0)
                    FROM payment_events
                    WHERE payer_id = :buyer_id AND payment_type = 'buyer_deposit'
                      AND status = 'completed'
                    """
                ),
                {"buyer_id": buyer_id},
            )
        ).scalar_one()

        active = (
            await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE buyer_id = :buyer_id AND stage <> ALL(:terminal)"
                ),
                {"buyer_id": buyer_id, "terminal": list(_TERMINAL)},
            )
        ).scalar_one()

        return WalletTotals(
            in_escrow_kobo=int(escrow.in_escrow if escrow else 0),
            escrow_deal_count=int(escrow.deals if escrow else 0),
            total_invested_kobo=int(invested),
            active_property_count=int(active),
        )

    async def active_payments(self, buyer_id: UUID) -> list[ActivePaymentRow]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT t.id, t.listing_id, t.agreed_price_kobo, t.stage,
                           pl.title AS property_title,
                           COALESCE((
                               SELECT SUM(pe.amount_kobo) FROM payment_events pe
                               WHERE pe.transaction_id = t.id AND pe.payer_id = t.buyer_id
                                 AND pe.status = 'completed'
                           ), 0) AS paid
                    FROM transactions t
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    WHERE t.buyer_id = :buyer_id AND t.stage <> ALL(:terminal)
                    ORDER BY t.created_at DESC
                    """
                ),
                {"buyer_id": buyer_id, "terminal": list(_TERMINAL)},
            )
        ).all()
        return [
            ActivePaymentRow(
                transaction_id=r.id,
                listing_id=r.listing_id,
                property_title=r.property_title,
                paid_kobo=int(r.paid),
                total_kobo=int(r.agreed_price_kobo),
                stage=r.stage,
            )
            for r in rows
        ]

    async def payment_history(self, buyer_id: UUID) -> list[PaymentRow]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT pe.id, pe.payment_type, pe.amount_kobo, pe.status, pe.provider,
                           pe.provider_reference, pe.transaction_id, pe.created_at,
                           pl.title AS property_title
                    FROM payment_events pe
                    LEFT JOIN transactions t ON t.id = pe.transaction_id
                    LEFT JOIN property_listings pl ON pl.id = t.listing_id
                    WHERE pe.payer_id = :buyer_id
                    ORDER BY pe.created_at DESC
                    """
                ),
                {"buyer_id": buyer_id},
            )
        ).all()
        return [
            PaymentRow(
                id=r.id,
                payment_type=r.payment_type,
                amount_kobo=int(r.amount_kobo),
                status=r.status,
                provider=r.provider,
                provider_reference=r.provider_reference,
                transaction_id=r.transaction_id,
                property_title=r.property_title,
                created_at=r.created_at,
            )
            for r in rows
        ]
