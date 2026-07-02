"""Financing summary for the buyer's loan page (SCRUM-94).

Backs GET /transactions/{id}/financing-summary. Gives the buyer's loan calculator
everything it needs in one call: the property (title, location, price, cover
image), the agreed price, the 50%-of-price loan cap (CLAUDE.md §8), and — if the
buyer has already applied — the existing loan's id + status so the page can route
them to their application instead of starting a new one.

Read-only, non-§11: no application is created and no money/state moves here. The
buyer may only see their OWN deal's summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.listing_repo import ListingRepository, PropertySummary
from app.repositories.transaction_repo import LatestLoan, TransactionRepository
from app.security import CurrentUser

# Max loan = 50% of the agreed price (CLAUDE.md §8 rule 5). Kept in sync with
# loan-service's loan_cap_bps; the buyer's calculator only needs the ceiling.
_LOAN_CAP_BPS = 5000


class TransactionNotFound(Exception):
    pass


class NotTransactionBuyer(Exception):
    pass


class PropertyNotFound(Exception):
    pass


@dataclass(frozen=True)
class FinancingSummary:
    transaction_id: UUID
    stage: str
    agreed_price_kobo: int
    max_loan_kobo: int
    property: PropertySummary
    existing_loan: LatestLoan | None


class FinancingSummaryService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        listings: ListingRepository,
    ) -> None:
        self._transactions = transactions
        self._listings = listings

    async def get(self, transaction_id: UUID, caller: CurrentUser) -> FinancingSummary:
        txn = await self._transactions.get_status(transaction_id)
        if txn is None:
            raise TransactionNotFound
        if txn.buyer_id != caller.user_id:
            raise NotTransactionBuyer

        property_ = await self._listings.get_property_summary(txn.listing_id)
        if property_ is None:
            raise PropertyNotFound

        existing = await self._transactions.get_latest_loan(transaction_id)
        max_loan_kobo = txn.agreed_price_kobo * _LOAN_CAP_BPS // 10_000
        return FinancingSummary(
            transaction_id=transaction_id,
            stage=txn.stage,
            agreed_price_kobo=txn.agreed_price_kobo,
            max_loan_kobo=max_loan_kobo,
            property=property_,
            existing_loan=existing,
        )
