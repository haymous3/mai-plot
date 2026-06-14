"""ListingExpiryService — expire + warn passes, with stubs."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.listing_expiry import ListingExpiryService


class _StubRepo:
    def __init__(self, *, expired: list[UUID], warn: list[UUID]) -> None:
        self._expired = expired
        self._warn = warn
        self.marked: list[UUID] = []

    async def list_active_expired(self, *, limit: int = 500) -> list[UUID]:
        return self._expired

    async def mark_expired(self, listing_id: UUID) -> None:
        self.marked.append(listing_id)

    async def list_due_for_expiry_warning(
        self, *, window_hours: int, limit: int = 500
    ) -> list[UUID]:
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


def _service(
    repo: _StubRepo, audit: _StubAudit, index_sync: _StubIndexSync | None
) -> ListingExpiryService:
    return ListingExpiryService(
        listings=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        index_sync=index_sync,  # type: ignore[arg-type]
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
async def test_warns_due_listings() -> None:
    c = uuid4()
    repo = _StubRepo(expired=[], warn=[c])
    audit = _StubAudit()
    result = await _service(repo, audit, None).run()

    assert result.warned == 1
    assert audit.actions == ["listing.expiry_warning"]


@pytest.mark.asyncio
async def test_nothing_due_is_noop() -> None:
    repo = _StubRepo(expired=[], warn=[])
    audit, index_sync = _StubAudit(), _StubIndexSync()
    result = await _service(repo, audit, index_sync).run()

    assert result.expired == 0 and result.warned == 0
    assert repo.marked == []
    assert index_sync.synced == []
    assert audit.actions == []
