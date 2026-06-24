"""ListingExpiryService — expire + warn passes (with seller notify), with stubs."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import ExpiryWarningTarget
from app.services.listing_expiry import ListingExpiryService


class _StubRepo:
    def __init__(self, *, expired: list[UUID], warn: list[ExpiryWarningTarget]) -> None:
        self._expired = expired
        self._warn = warn
        self.marked: list[UUID] = []

    async def list_active_expired(self, *, limit: int = 500) -> list[UUID]:
        return self._expired

    async def mark_expired(self, listing_id: UUID) -> None:
        self.marked.append(listing_id)

    async def list_due_for_expiry_warning(
        self, *, window_hours: int, limit: int = 500
    ) -> list[ExpiryWarningTarget]:
        return self._warn


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


class _StubIndexSync:
    def __init__(self) -> None:
        self.synced: list[UUID] = []

    async def sync_safe(self, listing_id: UUID) -> None:
        self.synced.append(listing_id)


class _RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def expiry_warning(self, *, seller_id: UUID, listing_id: UUID) -> None:
        self.calls.append((seller_id, listing_id))


def _service(
    repo: _StubRepo,
    audit: _StubAudit,
    index_sync: _StubIndexSync | None,
    notifier: _RecordingNotifier | None = None,
) -> ListingExpiryService:
    return ListingExpiryService(
        listings=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        index_sync=index_sync,  # type: ignore[arg-type]
        notifier=notifier,
    )


@pytest.mark.asyncio
async def test_expires_past_due_audits_and_syncs_index() -> None:
    a, b = uuid4(), uuid4()
    repo = _StubRepo(expired=[a, b], warn=[])
    audit, index_sync = _StubAudit(), _StubIndexSync()
    result = await _service(repo, audit, index_sync).run()

    assert result.expired == 2
    assert repo.marked == [a, b]
    assert index_sync.synced == [a, b]
    assert audit.actions == ["listing.expired", "listing.expired"]


@pytest.mark.asyncio
async def test_warns_due_listings_and_notifies_seller() -> None:
    listing_id, seller_id = uuid4(), uuid4()
    repo = _StubRepo(
        expired=[], warn=[ExpiryWarningTarget(listing_id=listing_id, seller_id=seller_id)]
    )
    audit = _StubAudit()
    notifier = _RecordingNotifier()
    result = await _service(repo, audit, None, notifier).run()

    assert result.warned == 1
    assert audit.actions == ["listing.expiry_warning"]
    assert notifier.calls == [(seller_id, listing_id)]


@pytest.mark.asyncio
async def test_nothing_due_is_noop() -> None:
    repo = _StubRepo(expired=[], warn=[])
    audit, index_sync = _StubAudit(), _StubIndexSync()
    notifier = _RecordingNotifier()
    result = await _service(repo, audit, index_sync, notifier).run()

    assert result.expired == 0 and result.warned == 0
    assert repo.marked == []
    assert index_sync.synced == []
    assert audit.actions == []
    assert notifier.calls == []
