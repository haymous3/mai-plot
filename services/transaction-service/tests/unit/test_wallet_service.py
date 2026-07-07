"""Unit tests for WalletService (SCRUM-95)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.wallet_repo import ActivePaymentRow, PaymentRow, WalletTotals
from app.services.wallet import WalletService

pytestmark = pytest.mark.asyncio


class _StubRepo:
    def __init__(self) -> None:
        self.totals_ret = WalletTotals(
            in_escrow_kobo=1_200_000_000,
            escrow_deal_count=2,
            total_invested_kobo=6_750_000_000,
            active_property_count=3,
        )
        self.active = [
            ActivePaymentRow(
                transaction_id=uuid4(),
                listing_id=uuid4(),
                property_title="5 Bedroom",
                paid_kobo=3_000_000_000,
                total_kobo=12_000_000_000,
                stage="payment_held",
            )
        ]
        self.history = [
            PaymentRow(
                id=uuid4(),
                payment_type="buyer_deposit",
                amount_kobo=3_000_000_000,
                status="completed",
                provider="paystack",
                provider_reference="ref-1",
                transaction_id=uuid4(),
                property_title="5 Bedroom",
                created_at=datetime.now(UTC),
            )
        ]

    async def totals(self, buyer_id: UUID) -> WalletTotals:
        return self.totals_ret

    async def active_payments(self, buyer_id: UUID) -> list[ActivePaymentRow]:
        return self.active

    async def payment_history(self, buyer_id: UUID) -> list[PaymentRow]:
        return self.history


async def test_summary_maps_totals_and_active_payments() -> None:
    service = WalletService(wallet=_StubRepo())  # type: ignore[arg-type]
    summary = await service.summary(uuid4())
    assert summary.in_escrow_kobo == 1_200_000_000
    assert summary.total_invested_kobo == 6_750_000_000
    assert summary.active_property_count == 3
    assert summary.active_payments[0].paid_kobo == 3_000_000_000
    assert summary.active_payments[0].total_kobo == 12_000_000_000


async def test_payments_maps_history() -> None:
    service = WalletService(wallet=_StubRepo())  # type: ignore[arg-type]
    payments = await service.payments(uuid4())
    assert len(payments.data) == 1
    assert payments.data[0].payment_type == "buyer_deposit"
    assert payments.data[0].status == "completed"
