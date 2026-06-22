"""TransactionStatusService — authz, validity, event + audit writes."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.transaction_repo import TransactionStatus
from app.security import CurrentUser
from app.services.transaction_status import (
    InvalidStateTransition,
    NotTransactionParty,
    TransactionNotFound,
    TransactionStatusService,
)

_BUYER = CurrentUser(user_id=uuid4(), role="buyer")
_SELLER = CurrentUser(user_id=uuid4(), role="seller")
_ADMIN = CurrentUser(user_id=uuid4(), role="admin")
_STRANGER = CurrentUser(user_id=uuid4(), role="buyer")
_LISTING = uuid4()


class _StubTxnRepo:
    def __init__(self, status: TransactionStatus | None) -> None:
        self._status = status
        self.updated_to: str | None = None
        self.events: list[tuple[str, str]] = []

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        return self._status

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        self.updated_to = stage

    async def append_event(
        self, *, from_stage: str | None, to_stage: str, **kwargs: object
    ) -> None:
        self.events.append((from_stage or "", to_stage))


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


class _StubListingRepo:
    def __init__(self) -> None:
        self.released: list[UUID] = []
        self.sold: list[UUID] = []

    async def release_lock(self, listing_id: UUID) -> None:
        self.released.append(listing_id)

    async def mark_sold(self, listing_id: UUID) -> None:
        self.sold.append(listing_id)


def _status(stage: str = "offer_accepted") -> TransactionStatus:
    return TransactionStatus(
        stage=stage, buyer_id=_BUYER.user_id, seller_id=_SELLER.user_id, listing_id=_LISTING
    )


def _service(
    status: TransactionStatus | None,
) -> tuple[TransactionStatusService, _StubTxnRepo, _StubAudit, _StubListingRepo]:
    repo = _StubTxnRepo(status)
    audit = _StubAudit()
    listings = _StubListingRepo()
    svc = TransactionStatusService(
        transactions=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        listings=listings,  # type: ignore[arg-type]
    )
    return svc, repo, audit, listings


@pytest.mark.asyncio
async def test_valid_transition_updates_appends_event_and_audits() -> None:
    svc, repo, audit, listings = _service(_status("offer_accepted"))
    stage = await svc.change_status(
        transaction_id=uuid4(), caller=_BUYER, target_stage="inspection_scheduled"
    )
    assert stage == "inspection_scheduled"
    assert repo.updated_to == "inspection_scheduled"
    assert repo.events == [("offer_accepted", "inspection_scheduled")]
    assert audit.actions == ["transaction.inspection_scheduled"]
    # A mid-deal transition leaves the listing lock untouched.
    assert listings.released == [] and listings.sold == []


@pytest.mark.asyncio
async def test_seller_and_admin_may_transition() -> None:
    for caller in (_SELLER, _ADMIN):
        svc, repo, _, _ = _service(_status("offer_accepted"))
        await svc.change_status(transaction_id=uuid4(), caller=caller, target_stage="cancelled")
        assert repo.updated_to == "cancelled"


@pytest.mark.asyncio
async def test_cancel_releases_the_listing_lock() -> None:
    svc, _, _, listings = _service(_status("offer_accepted"))
    await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="cancelled")
    assert listings.released == [_LISTING]
    assert listings.sold == []


@pytest.mark.asyncio
async def test_complete_marks_the_listing_sold() -> None:
    svc, _, _, listings = _service(_status("title_held"))
    await svc.change_status(transaction_id=uuid4(), caller=_SELLER, target_stage="completed")
    assert listings.sold == [_LISTING]
    assert listings.released == []


@pytest.mark.asyncio
async def test_unknown_transaction_raises() -> None:
    svc, _, _, _ = _service(None)
    with pytest.raises(TransactionNotFound):
        await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="cancelled")


@pytest.mark.asyncio
async def test_non_party_is_forbidden() -> None:
    svc, repo, _, _ = _service(_status("offer_accepted"))
    with pytest.raises(NotTransactionParty):
        await svc.change_status(transaction_id=uuid4(), caller=_STRANGER, target_stage="cancelled")
    assert repo.updated_to is None


@pytest.mark.asyncio
async def test_illegal_transition_raises_and_does_not_write() -> None:
    svc, repo, audit, listings = _service(_status("offer_accepted"))
    with pytest.raises(InvalidStateTransition):
        await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="completed")
    assert repo.updated_to is None
    assert repo.events == []
    assert audit.actions == []
    assert listings.released == [] and listings.sold == []
