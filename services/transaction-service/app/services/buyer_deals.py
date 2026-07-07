"""List a buyer's deals for the "Your Active Deals" surface (SCRUM-95).

Read-only: returns the caller's own transactions (newest first) with the
property title joined in. Non-§11 — no money/state-machine, a scoped read.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.transaction_repo import TransactionRepository
from app.schemas.transaction import DealItem, DealsResponse


class BuyerDealsService:
    def __init__(self, *, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    async def list_for_buyer(self, buyer_id: UUID) -> DealsResponse:
        rows = await self._transactions.list_for_buyer(buyer_id)
        return DealsResponse(
            data=[
                DealItem(
                    transaction_id=r.id,
                    listing_id=r.listing_id,
                    stage=r.stage,
                    agreed_price_kobo=r.agreed_price_kobo,
                    property_title=r.property_title,
                    sale_type=r.sale_type,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
