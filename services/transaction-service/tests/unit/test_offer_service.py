"""OfferService — create/accept/counter/reject/respond, validations, expiry."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import ListingForOffer
from app.repositories.offer_repo import OfferRow
from app.repositories.transaction_repo import ListingLock
from app.security import CurrentUser
from app.services.offer_service import (
    AcceptResult,
    CannotOfferOwnListing,
    ListingNotAvailable,
    ListingNotFound,
    NotOfferBuyer,
    NotOfferSeller,
    OfferExpired,
    OfferNotActionable,
    OfferService,
)

_BUYER = CurrentUser(user_id=uuid4(), role="buyer")
_SELLER = CurrentUser(user_id=uuid4(), role="seller")
_LISTING = uuid4()


def _active_listing(**over: object) -> ListingForOffer:
    base = {"seller_id": _SELLER.user_id, "status": "active", "expires_at": None}
    base.update(over)
    return ListingForOffer(**base)  # type: ignore[arg-type]


class _StubListingRepo:
    def __init__(self, listing: ListingForOffer | None) -> None:
        self._listing = listing
        self.under_offer: list[UUID] = []
        self.released: list[UUID] = []
        self.sold: list[UUID] = []

    async def get_for_offer(self, listing_id: UUID) -> ListingForOffer | None:
        return self._listing

    async def mark_under_offer(self, listing_id: UUID) -> None:
        self.under_offer.append(listing_id)

    async def release_lock(self, listing_id: UUID) -> None:
        self.released.append(listing_id)
        if self._listing is not None:  # model the under_offer → active flip
            self._listing = replace(self._listing, status="active")

    async def mark_sold(self, listing_id: UUID) -> None:
        self.sold.append(listing_id)


class _StubOfferRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, OfferRow] = {}

    def seed(self, **over: object) -> OfferRow:
        row = OfferRow(
            id=uuid4(),
            listing_id=_LISTING,
            buyer_id=_BUYER.user_id,
            seller_id=_SELLER.user_id,
            offered_price_kobo=5_000_000_000,
            counter_price_kobo=None,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        row = replace(row, **over)  # type: ignore[arg-type]
        self.rows[row.id] = row
        return row

    async def create(
        self, *, listing_id: UUID, buyer_id: UUID, offered_price_kobo: int, expires_at: datetime
    ) -> UUID:
        row = OfferRow(
            id=uuid4(),
            listing_id=listing_id,
            buyer_id=buyer_id,
            seller_id=_SELLER.user_id,  # the join surfaces the listing's seller
            offered_price_kobo=offered_price_kobo,
            counter_price_kobo=None,
            status="pending",
            expires_at=expires_at,
        )
        self.rows[row.id] = row
        return row.id

    async def get(self, offer_id: UUID) -> OfferRow | None:
        return self.rows.get(offer_id)

    async def set_status(self, offer_id: UUID, *, status: str) -> None:
        self.rows[offer_id] = replace(self.rows[offer_id], status=status)

    async def set_countered(self, offer_id: UUID, *, counter_price_kobo: int) -> None:
        self.rows[offer_id] = replace(
            self.rows[offer_id], status="countered", counter_price_kobo=counter_price_kobo
        )

    async def set_accepted(self, offer_id: UUID) -> None:
        self.rows[offer_id] = replace(self.rows[offer_id], status="accepted")


class _StubTxnRepo:
    def __init__(self, lock: ListingLock | None = None) -> None:
        self.created: list[dict[str, object]] = []
        self.events: list[str] = []
        self.updated: list[tuple[UUID, str]] = []
        self._lock = lock

    async def create_at_offer_accepted(self, **kwargs: object) -> UUID:
        self.created.append(kwargs)
        return uuid4()

    async def append_event(self, **kwargs: object) -> None:
        self.events.append(str(kwargs["event_type"]))

    async def get_lock_for_listing(self, listing_id: UUID) -> ListingLock | None:
        return self._lock

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        self.updated.append((transaction_id, stage))


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(
    listing: ListingForOffer | None,
    offers: _StubOfferRepo | None = None,
    txns: _StubTxnRepo | None = None,
) -> tuple[OfferService, _StubOfferRepo, _StubListingRepo, _StubTxnRepo]:
    o = offers or _StubOfferRepo()
    listings_repo = _StubListingRepo(listing)
    t = txns or _StubTxnRepo()
    svc = OfferService(
        offers=o,  # type: ignore[arg-type]
        listings=listings_repo,  # type: ignore[arg-type]
        transactions=t,  # type: ignore[arg-type]
        audit=_StubAudit(),  # type: ignore[arg-type]
    )
    return svc, o, listings_repo, t


# -- create ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_offer_happy_path() -> None:
    svc, offers, _, _ = _service(_active_listing())
    offer = await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=4_000_000_000)
    assert offer.status == "pending"
    assert offer.seller_id == _SELLER.user_id
    assert offer.offered_price_kobo == 4_000_000_000


@pytest.mark.asyncio
async def test_create_offer_on_unknown_listing_raises() -> None:
    svc, _, _, _ = _service(None)
    with pytest.raises(ListingNotFound):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)


@pytest.mark.asyncio
async def test_cannot_offer_on_own_listing() -> None:
    svc, _, _, _ = _service(_active_listing(seller_id=_BUYER.user_id))
    with pytest.raises(CannotOfferOwnListing):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)


@pytest.mark.asyncio
async def test_offer_on_under_offer_listing_is_conflict() -> None:
    # No transaction lock on record → genuinely locked, refused.
    svc, _, _, _ = _service(_active_listing(status="under_offer"))
    with pytest.raises(ListingNotAvailable):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)


@pytest.mark.asyncio
async def test_offer_reopens_listing_when_72h_lock_lapsed() -> None:
    lock = ListingLock(
        transaction_id=uuid4(),
        stage="offer_accepted",
        lock_expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    txns = _StubTxnRepo(lock=lock)
    svc, _, listings, _ = _service(_active_listing(status="under_offer"), txns=txns)

    offer = await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=4_000_000_000)

    assert offer.status == "pending"  # the new offer went through
    assert listings.released == [_LISTING]  # listing reopened
    assert txns.updated == [(lock.transaction_id, "cancelled")]  # stale deal cancelled


@pytest.mark.asyncio
async def test_offer_refused_while_72h_lock_still_live() -> None:
    lock = ListingLock(
        transaction_id=uuid4(),
        stage="offer_accepted",
        lock_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    txns = _StubTxnRepo(lock=lock)
    svc, _, listings, _ = _service(_active_listing(status="under_offer"), txns=txns)

    with pytest.raises(ListingNotAvailable):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)
    assert listings.released == []


@pytest.mark.asyncio
async def test_offer_refused_when_deal_progressed_past_offer_accepted() -> None:
    # Lock window elapsed, but the deal is live (inspection scheduled) — the
    # listing stays locked; an active deal is not abandoned.
    lock = ListingLock(
        transaction_id=uuid4(),
        stage="inspection_scheduled",
        lock_expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    txns = _StubTxnRepo(lock=lock)
    svc, _, listings, _ = _service(_active_listing(status="under_offer"), txns=txns)

    with pytest.raises(ListingNotAvailable):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)
    assert listings.released == []
    assert txns.updated == []


@pytest.mark.asyncio
async def test_offer_on_expired_listing_is_conflict() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    svc, _, _, _ = _service(_active_listing(expires_at=past))
    with pytest.raises(ListingNotAvailable):
        await svc.create_offer(buyer=_BUYER, listing_id=_LISTING, amount_kobo=1)


# -- accept ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_creates_transaction_and_locks_listing() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed()
    svc, _, listings, txns = _service(_active_listing(), offers=offers)

    result = await svc.accept_offer(seller=_SELLER, offer_id=offer.id)

    assert isinstance(result, AcceptResult)
    assert offers.rows[offer.id].status == "accepted"
    assert listings.under_offer == [_LISTING]
    assert txns.events == ["offer_accepted"]
    assert txns.created[0]["agreed_price_kobo"] == offer.offered_price_kobo


@pytest.mark.asyncio
async def test_only_seller_can_accept() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed()
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    with pytest.raises(NotOfferSeller):
        await svc.accept_offer(seller=_BUYER, offer_id=offer.id)


@pytest.mark.asyncio
async def test_accept_non_pending_offer_is_not_actionable() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed(status="rejected")
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    with pytest.raises(OfferNotActionable):
        await svc.accept_offer(seller=_SELLER, offer_id=offer.id)


@pytest.mark.asyncio
async def test_accept_expired_offer_is_refused() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    with pytest.raises(OfferExpired):
        await svc.accept_offer(seller=_SELLER, offer_id=offer.id)
    # Status is not mutated (the offers CHECK has no 'expired' value).
    assert offers.rows[offer.id].status == "pending"


@pytest.mark.asyncio
async def test_accept_when_listing_no_longer_active_is_conflict() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed()
    svc, _, _, _ = _service(_active_listing(status="under_offer"), offers=offers)
    with pytest.raises(ListingNotAvailable):
        await svc.accept_offer(seller=_SELLER, offer_id=offer.id)


# -- counter / reject / respond -------------------------------------------


@pytest.mark.asyncio
async def test_counter_then_buyer_accepts_uses_counter_price() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed()
    svc, _, listings, txns = _service(_active_listing(), offers=offers)

    countered = await svc.counter_offer(
        seller=_SELLER, offer_id=offer.id, counter_amount_kobo=6_000_000_000
    )
    assert countered.status == "countered"
    assert countered.counter_price_kobo == 6_000_000_000

    result = await svc.respond_to_counter(buyer=_BUYER, offer_id=offer.id, action="accept")
    assert isinstance(result, AcceptResult)
    assert txns.created[0]["agreed_price_kobo"] == 6_000_000_000
    assert listings.under_offer == [_LISTING]


@pytest.mark.asyncio
async def test_buyer_rejects_counter() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed(status="countered", counter_price_kobo=6_000_000_000)
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    result = await svc.respond_to_counter(buyer=_BUYER, offer_id=offer.id, action="reject")
    assert not isinstance(result, AcceptResult)
    assert offers.rows[offer.id].status == "rejected"


@pytest.mark.asyncio
async def test_only_buyer_can_respond_to_counter() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed(status="countered", counter_price_kobo=1)
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    with pytest.raises(NotOfferBuyer):
        await svc.respond_to_counter(buyer=_SELLER, offer_id=offer.id, action="accept")


@pytest.mark.asyncio
async def test_respond_when_not_countered_is_not_actionable() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed(status="pending")
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    with pytest.raises(OfferNotActionable):
        await svc.respond_to_counter(buyer=_BUYER, offer_id=offer.id, action="accept")


@pytest.mark.asyncio
async def test_seller_rejects_offer() -> None:
    offers = _StubOfferRepo()
    offer = offers.seed()
    svc, _, _, _ = _service(_active_listing(), offers=offers)
    rejected = await svc.reject_offer(seller=_SELLER, offer_id=offer.id)
    assert rejected.status == "rejected"
