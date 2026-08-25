"""Unit tests for FinancingSummaryService (SCRUM-94)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import PropertySummary
from app.repositories.transaction_repo import LatestLoan, TransactionStatus
from app.security import CurrentUser
from app.services.financing_summary import (
    FinancingSummaryService,
    NotTransactionBuyer,
    PropertyNotFound,
    TransactionNotFound,
)

pytestmark = pytest.mark.asyncio

_BUYER = uuid4()
_LISTING = uuid4()


def _status(*, buyer: UUID = _BUYER, price: int = 60_000_000) -> TransactionStatus:
    return TransactionStatus(
        stage="inspection_completed",
        buyer_id=buyer,
        seller_id=uuid4(),
        listing_id=_LISTING,
        agreed_price_kobo=price,
        platform_fee_kobo=None,
    )


def _property() -> PropertySummary:
    return PropertySummary(
        title="4 Bedroom Duplex",
        property_type="house",
        address_text="Ikeja GRA",
        lga="Ikeja",
        state="Lagos",
        sale_type="normal",
        asking_price_kobo=60_000_000,
        primary_image_url="https://cdn.maihomme.com/x.jpg",
    )


class _StubTransactions:
    def __init__(
        self, *, status: TransactionStatus | None, latest_loan: LatestLoan | None = None
    ) -> None:
        self._status = status
        self._latest_loan = latest_loan

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        return self._status

    async def get_latest_loan(self, transaction_id: UUID) -> LatestLoan | None:
        return self._latest_loan


class _StubListings:
    def __init__(self, *, property_: PropertySummary | None) -> None:
        self._property = property_

    async def get_property_summary(self, listing_id: UUID) -> PropertySummary | None:
        return self._property


def _service(transactions: _StubTransactions, listings: _StubListings) -> FinancingSummaryService:
    return FinancingSummaryService(
        transactions=transactions,  # type: ignore[arg-type]
        listings=listings,  # type: ignore[arg-type]
    )


async def test_summary_caps_loan_at_half_price_no_existing_loan() -> None:
    svc = _service(_StubTransactions(status=_status()), _StubListings(property_=_property()))
    summary = await svc.get(uuid4(), CurrentUser(user_id=_BUYER, role="buyer"))
    assert summary.agreed_price_kobo == 60_000_000
    assert summary.max_loan_kobo == 30_000_000  # 50%
    assert summary.property.title == "4 Bedroom Duplex"
    assert summary.existing_loan is None


async def test_summary_surfaces_existing_loan() -> None:
    loan = LatestLoan(loan_id=uuid4(), status="under_review")
    svc = _service(
        _StubTransactions(status=_status(), latest_loan=loan),
        _StubListings(property_=_property()),
    )
    summary = await svc.get(uuid4(), CurrentUser(user_id=_BUYER, role="buyer"))
    assert summary.existing_loan == loan


async def test_unknown_transaction_raises() -> None:
    svc = _service(_StubTransactions(status=None), _StubListings(property_=_property()))
    with pytest.raises(TransactionNotFound):
        await svc.get(uuid4(), CurrentUser(user_id=_BUYER, role="buyer"))


async def test_non_buyer_forbidden() -> None:
    svc = _service(_StubTransactions(status=_status()), _StubListings(property_=_property()))
    with pytest.raises(NotTransactionBuyer):
        await svc.get(uuid4(), CurrentUser(user_id=uuid4(), role="buyer"))


async def test_missing_listing_raises() -> None:
    svc = _service(_StubTransactions(status=_status()), _StubListings(property_=None))
    with pytest.raises(PropertyNotFound):
        await svc.get(uuid4(), CurrentUser(user_id=_BUYER, role="buyer"))
