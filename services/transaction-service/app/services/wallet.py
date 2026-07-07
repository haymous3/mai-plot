"""Read-only buyer wallet service (SCRUM-95).

Assembles the "My Wallet" view — escrow/invested totals, active property
payments, and payment history — from existing tables scoped to the buyer. No
writes, no wallet-balance primitive. Non-§11.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.wallet_repo import WalletRepository
from app.schemas.wallet import (
    ActivePaymentOut,
    PaymentOut,
    PaymentsOut,
    WalletSummaryOut,
)


class WalletService:
    def __init__(self, *, wallet: WalletRepository) -> None:
        self._wallet = wallet

    async def summary(self, buyer_id: UUID) -> WalletSummaryOut:
        totals = await self._wallet.totals(buyer_id)
        payments = await self._wallet.active_payments(buyer_id)
        return WalletSummaryOut(
            in_escrow_kobo=totals.in_escrow_kobo,
            escrow_deal_count=totals.escrow_deal_count,
            total_invested_kobo=totals.total_invested_kobo,
            active_property_count=totals.active_property_count,
            active_payments=[
                ActivePaymentOut(
                    transaction_id=p.transaction_id,
                    listing_id=p.listing_id,
                    property_title=p.property_title,
                    paid_kobo=p.paid_kobo,
                    total_kobo=p.total_kobo,
                    stage=p.stage,
                )
                for p in payments
            ],
        )

    async def payments(self, buyer_id: UUID) -> PaymentsOut:
        rows = await self._wallet.payment_history(buyer_id)
        return PaymentsOut(
            data=[
                PaymentOut(
                    id=r.id,
                    payment_type=r.payment_type,
                    amount_kobo=r.amount_kobo,
                    status=r.status,
                    provider=r.provider,
                    provider_reference=r.provider_reference,
                    transaction_id=r.transaction_id,
                    property_title=r.property_title,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
