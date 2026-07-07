"""List a seller's transactions for the seller "Transactions" surface (SCRUM-98).

Read-only, non-§11: the caller's own sales (newest first) with the property title
joined. The buyer stays masked to a short reference until the deal completes (§8).
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.transaction_repo import TransactionRepository
from app.schemas.transaction import SellerDealItem, SellerDealsResponse


class SellerDealsService:
    def __init__(self, *, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    async def list_for_seller(self, seller_id: UUID) -> SellerDealsResponse:
        rows = await self._transactions.list_for_seller(seller_id)
        return SellerDealsResponse(
            data=[
                SellerDealItem(
                    transaction_id=r.id,
                    listing_id=r.listing_id,
                    buyer_ref=str(r.buyer_id)[:8],
                    stage=r.stage,
                    agreed_price_kobo=r.agreed_price_kobo,
                    property_title=r.property_title,
                    sale_type=r.sale_type,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )
