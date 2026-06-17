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


def _status(stage: str = "offer_accepted") -> TransactionStatus:
    return TransactionStatus(stage=stage, buyer_id=_BUYER.user_id, seller_id=_SELLER.user_id)


def _service(
    status: TransactionStatus | None,
) -> tuple[TransactionStatusService, _StubTxnRepo, _StubAudit]:
    repo = _StubTxnRepo(status)
    audit = _StubAudit()
    svc = TransactionStatusService(transactions=repo, audit=audit)  # type: ignore[arg-type]
    return svc, repo, audit


@pytest.mark.asyncio
async def test_valid_transition_updates_appends_event_and_audits() -> None:
    svc, repo, audit = _service(_status("offer_accepted"))
    stage = await svc.change_status(
        transaction_id=uuid4(), caller=_BUYER, target_stage="inspection_scheduled"
    )
    assert stage == "inspection_scheduled"
    assert repo.updated_to == "inspection_scheduled"
    assert repo.events == [("offer_accepted", "inspection_scheduled")]
    assert audit.actions == ["transaction.inspection_scheduled"]


@pytest.mark.asyncio
async def test_seller_and_admin_may_transition() -> None:
    for caller in (_SELLER, _ADMIN):
        svc, repo, _ = _service(_status("offer_accepted"))
        await svc.change_status(transaction_id=uuid4(), caller=caller, target_stage="cancelled")
        assert repo.updated_to == "cancelled"


@pytest.mark.asyncio
async def test_unknown_transaction_raises() -> None:
    svc, _, _ = _service(None)
    with pytest.raises(TransactionNotFound):
        await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="cancelled")


@pytest.mark.asyncio
async def test_non_party_is_forbidden() -> None:
    svc, repo, _ = _service(_status("offer_accepted"))
    with pytest.raises(NotTransactionParty):
        await svc.change_status(transaction_id=uuid4(), caller=_STRANGER, target_stage="cancelled")
    assert repo.updated_to is None


@pytest.mark.asyncio
async def test_illegal_transition_raises_and_does_not_write() -> None:
    svc, repo, audit = _service(_status("offer_accepted"))
    with pytest.raises(InvalidStateTransition):
        await svc.change_status(transaction_id=uuid4(), caller=_BUYER, target_stage="completed")
    assert repo.updated_to is None
    assert repo.events == []
    assert audit.actions == []
