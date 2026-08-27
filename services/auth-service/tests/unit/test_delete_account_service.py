"""Unit tests for DeleteAccountService (SCRUM-188).

The property that matters most here is FAIL-CLOSED: an active-deal check that
cannot be evaluated must refuse the deletion, never wave it through. That
inverts the fail-OPEN convention used for caches and rate limiters, so it is
worth pinning down with tests rather than leaving to review.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.deals import DealCheckUnavailable, InMemoryDealChecker
from app.adapters.document_storage import DocumentStorageError, InMemoryDocumentStorage
from app.services.delete_account import (
    AccountAlreadyGone,
    AccountHasActiveDeals,
    DeleteAccountService,
    DeleteCheckUnavailable,
)

pytestmark = pytest.mark.asyncio

_TOKEN = "header.payload.signature"


class _StubUsers:
    def __init__(self, *, deleted: bool = True, avatar_key: str | None = None) -> None:
        self._result = (deleted, avatar_key)
        self.calls: list[UUID] = []

    async def soft_delete(self, user_id: UUID) -> tuple[bool, str | None]:
        self.calls.append(user_id)
        return self._result


class _StubRefreshTokens:
    def __init__(self) -> None:
        self.revoked: list[UUID] = []

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        self.revoked.append(user_id)


class _ExplodingStorage(InMemoryDocumentStorage):
    async def delete(self, key: str) -> None:
        raise DocumentStorageError("bucket unreachable")


def _service(
    *,
    users: _StubUsers | None = None,
    refresh: _StubRefreshTokens | None = None,
    deals: InMemoryDealChecker | None = None,
    storage: InMemoryDocumentStorage | None = None,
) -> tuple[DeleteAccountService, _StubUsers, _StubRefreshTokens, InMemoryDocumentStorage]:
    users = users or _StubUsers()
    refresh = refresh or _StubRefreshTokens()
    storage = storage or InMemoryDocumentStorage()
    service = DeleteAccountService(
        users=users,  # type: ignore[arg-type]
        refresh_tokens=refresh,  # type: ignore[arg-type]
        deals=deals or InMemoryDealChecker(),
        storage=storage,
    )
    return service, users, refresh, storage


async def test_deletes_and_revokes_every_session() -> None:
    user_id = uuid4()
    service, users, refresh, _ = _service()

    await service.delete(user_id=user_id, bearer_token=_TOKEN)

    assert users.calls == [user_id]
    # A live access token would otherwise keep working until it expired.
    assert refresh.revoked == [user_id]


async def test_active_deal_blocks_deletion_before_any_write() -> None:
    service, users, refresh, _ = _service(deals=InMemoryDealChecker(has_active=True))

    with pytest.raises(AccountHasActiveDeals):
        await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    # The guard runs FIRST — nothing was written and no session was revoked.
    assert users.calls == []
    assert refresh.revoked == []


async def test_unavailable_guard_refuses_rather_than_assuming_no_deals() -> None:
    """Fail CLOSED. "We could not check" must never be treated as "all clear" —
    deleting an account over an unchecked escrow balance is not recoverable."""
    service, users, refresh, _ = _service(deals=InMemoryDealChecker(fail_next=True))

    with pytest.raises(DeleteCheckUnavailable):
        await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert users.calls == []
    assert refresh.revoked == []


async def test_the_callers_own_token_is_forwarded() -> None:
    """The transaction-service endpoint is caller-scoped, which is what lets us
    avoid inventing a service-to-service credential."""
    deals = InMemoryDealChecker()
    service, _, _, _ = _service(deals=deals)

    await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert deals.calls == [_TOKEN]


async def test_already_deleted_account_reports_gone() -> None:
    service, _, refresh, _ = _service(users=_StubUsers(deleted=False))

    with pytest.raises(AccountAlreadyGone):
        await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert refresh.revoked == []


async def test_profile_photo_is_really_deleted() -> None:
    """NDPR erasure: the row survives for CBN/AMLON, but a face photo has no
    retention basis, so the object itself goes."""
    storage = InMemoryDocumentStorage()
    key = "avatar/abc/def.png"
    await storage.put(key=key, data=b"\x89PNG\r\n\x1a\n", content_type="image/png")
    service, _, _, _ = _service(users=_StubUsers(avatar_key=key), storage=storage)

    await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert key not in storage.data


async def test_storage_failure_does_not_fail_a_committed_deletion() -> None:
    """The row no longer references the object, so the account IS deleted. An
    orphaned object is logged for the lifecycle sweep, not surfaced as an error
    on a deletion the user already committed to."""
    service, users, refresh, _ = _service(
        users=_StubUsers(avatar_key="avatar/abc/def.png"),
        storage=_ExplodingStorage(),
    )

    await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert len(users.calls) == 1
    assert len(refresh.revoked) == 1


async def test_deal_check_unavailable_is_not_swallowed_as_a_generic_error() -> None:
    """DeleteCheckUnavailable must be distinguishable from the other failures so
    the route can answer 503 (retryable) rather than 409 or 404."""
    service, _, _, _ = _service(deals=InMemoryDealChecker(fail_next=True))

    with pytest.raises(DeleteCheckUnavailable) as exc:
        await service.delete(user_id=uuid4(), bearer_token=_TOKEN)

    assert isinstance(exc.value.__cause__, DealCheckUnavailable)
