"""TransactionStatusService — authz, validity, event + audit writes."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.escrow_repo import EscrowBalance
from app.repositories.transaction_repo import TransactionStatus
from app.security import CurrentUser
from app.services.transaction_status import (
    EscrowNotFullyFunded,
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
        self.fee_set_to: int | None = None

    async def get_status(self, transaction_id: UUID) -> TransactionStatus | None:
        return self._status

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        self.updated_to = stage

    async def append_event(
        self, *, from_stage: str | None, to_stage: str, **kwargs: object
    ) -> None:
        self.events.append((from_stage or "", to_stage))

    async def set_platform_fee(self, transaction_id: UUID, *, fee_kobo: int) -> bool:
        self.fee_set_to = fee_kobo
        return True


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


class _StubEscrow:
    """Reports a fixed escrow balance — only consulted by the payment_held gate.
    Defaults high so non-payment_held transitions are unaffected."""

    def __init__(self, *, balance_kobo: int = 1_000_000_000_000) -> None:
        self._balance_kobo = balance_kobo

    async def balance(self, transaction_id: UUID) -> EscrowBalance:
        return EscrowBalance(
            transaction_id=transaction_id, balance_kobo=self._balance_kobo, pending_kobo=0
        )


def _status(
    stage: str = "offer_accepted",
    *,
    agreed_price_kobo: int = 5_000_000_000,
    platform_fee_kobo: int | None = None,
) -> TransactionStatus:
    return TransactionStatus(
        stage=stage,
        buyer_id=_BUYER.user_id,
        seller_id=_SELLER.user_id,
        listing_id=_LISTING,
        agreed_price_kobo=agreed_price_kobo,
        platform_fee_kobo=platform_fee_kobo,
    )


def _service(
    status: TransactionStatus | None,
    *,
    platform_fee_bps: int = 250,
    escrow_balance_kobo: int = 1_000_000_000_000,
) -> tuple[TransactionStatusService, _StubTxnRepo, _StubAudit, _StubListingRepo]:
    repo = _StubTxnRepo(status)
    audit = _StubAudit()
    listings = _StubListingRepo()
    svc = TransactionStatusService(
        transactions=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        listings=listings,  # type: ignore[arg-type]
        escrow=_StubEscrow(balance_kobo=escrow_balance_kobo),  # type: ignore[arg-type]
        platform_fee_bps=platform_fee_bps,
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
async def test_complete_sets_platform_fee_and_audits() -> None:
    # 2.5% of 5,000,000,000 kobo = 125,000,000 kobo.
    svc, repo, audit, _ = _service(_status("title_held", agreed_price_kobo=5_000_000_000))
    await svc.change_status(transaction_id=uuid4(), caller=_SELLER, target_stage="completed")
    assert repo.fee_set_to == 125_000_000
    assert "transaction.platform_fee_set" in audit.actions


@pytest.mark.asyncio
async def test_complete_does_not_recompute_an_existing_fee() -> None:
    svc, repo, audit, _ = _service(_status("title_held", platform_fee_kobo=999))
    await svc.change_status(transaction_id=uuid4(), caller=_SELLER, target_stage="completed")
    assert repo.fee_set_to is None  # not touched
    assert "transaction.platform_fee_set" not in audit.actions


@pytest.mark.asyncio
async def test_non_complete_transition_sets_no_fee() -> None:
    svc, repo, _, _ = _service(_status("offer_accepted"))
    await svc.change_status(
        transaction_id=uuid4(), caller=_BUYER, target_stage="inspection_scheduled"
    )
    assert repo.fee_set_to is None


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


# --- payment_held full-funding gate (SCRUM-146, §11) ------------------------


@pytest.mark.asyncio
async def test_payment_held_allowed_when_escrow_fully_funded() -> None:
    svc, repo, _, _ = _service(
        _status("inspection_completed", agreed_price_kobo=5_000_000_000),
        escrow_balance_kobo=5_000_000_000,  # exactly the agreed price
    )
    stage = await svc.change_status(
        transaction_id=uuid4(), caller=_BUYER, target_stage="payment_held"
    )
    assert stage == "payment_held"
    assert repo.updated_to == "payment_held"


@pytest.mark.asyncio
async def test_payment_held_allowed_when_over_funded() -> None:
    svc, repo, _, _ = _service(
        _status("inspection_completed", agreed_price_kobo=5_000_000_000),
        escrow_balance_kobo=6_000_000_000,
    )
    await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="payment_held")
    assert repo.updated_to == "payment_held"


@pytest.mark.asyncio
async def test_payment_held_blocked_when_underfunded_and_does_not_write() -> None:
    svc, repo, audit, _ = _service(
        _status("inspection_completed", agreed_price_kobo=5_000_000_000),
        escrow_balance_kobo=4_999_999_999,  # one kobo short
    )
    with pytest.raises(EscrowNotFullyFunded):
        await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="payment_held")
    assert repo.updated_to is None
    assert repo.events == []
    assert audit.actions == []


@pytest.mark.asyncio
async def test_payment_held_blocked_when_escrow_empty() -> None:
    svc, repo, _, _ = _service(
        _status("inspection_completed", agreed_price_kobo=5_000_000_000),
        escrow_balance_kobo=0,
    )
    with pytest.raises(EscrowNotFullyFunded):
        await svc.change_status(transaction_id=uuid4(), caller=_SELLER, target_stage="payment_held")
    assert repo.updated_to is None


@pytest.mark.asyncio
async def test_payment_held_gate_applies_to_admin_too() -> None:
    # No admin bypass (SCRUM-146 decision) — an admin cannot force an underfunded
    # deal to payment_held.
    svc, repo, _, _ = _service(
        _status("inspection_completed", agreed_price_kobo=5_000_000_000),
        escrow_balance_kobo=0,
    )
    with pytest.raises(EscrowNotFullyFunded):
        await svc.change_status(transaction_id=uuid4(), caller=_ADMIN, target_stage="payment_held")
    assert repo.updated_to is None
