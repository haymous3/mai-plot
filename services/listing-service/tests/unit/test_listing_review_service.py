"""ListingReviewService — approve/reject, validation, audit, reindex."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.listing_repo import OwnerStatus
from app.security import CurrentUser
from app.services.listing_review import (
    CommentRequired,
    ListingReviewService,
    NotPendingReview,
)
from app.services.listing_update import ListingNotFound

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


class _StubRepo:
    def __init__(self, owner: OwnerStatus | None) -> None:
        self._owner = owner
        self.review_call: dict[str, object] | None = None

    async def get_owner_status(self, listing_id: UUID) -> OwnerStatus | None:
        return self._owner

    async def set_review_status(
        self, listing_id: UUID, *, new_status: str, rejection_reason: str | None
    ) -> None:
        self.review_call = {"new_status": new_status, "rejection_reason": rejection_reason}


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _StubIndexer:
    def __init__(self) -> None:
        self.reindexed: list[UUID] = []

    async def reindex_safe(self, listing_id: UUID) -> None:
        self.reindexed.append(listing_id)


def _pending() -> OwnerStatus:
    return OwnerStatus(seller_id=uuid4(), status="pending_review", sale_type="normal")


def _service(
    repo: _StubRepo, audit: _StubAudit | None = None, indexer: _StubIndexer | None = None
) -> tuple[ListingReviewService, _StubAudit, _StubIndexer]:
    a = audit or _StubAudit()
    i = indexer or _StubIndexer()
    svc = ListingReviewService(
        listings=repo,  # type: ignore[arg-type]
        audit=a,  # type: ignore[arg-type]
        indexer=i,  # type: ignore[arg-type]
    )
    return svc, a, i


@pytest.mark.asyncio
async def test_approve_activates_audits_and_reindexes() -> None:
    repo = _StubRepo(_pending())
    svc, audit, indexer = _service(repo)
    lid = uuid4()
    result = await svc.review(listing_id=lid, admin=_ADMIN, action="approve", comment=None)

    assert result.status == "active"
    assert repo.review_call == {"new_status": "active", "rejection_reason": None}
    assert audit.records[0]["action"] == "listing.active"
    assert indexer.reindexed == [lid]


@pytest.mark.asyncio
async def test_reject_requires_comment() -> None:
    repo = _StubRepo(_pending())
    svc, audit, _ = _service(repo)
    with pytest.raises(CommentRequired):
        await svc.review(listing_id=uuid4(), admin=_ADMIN, action="reject", comment="   ")
    assert repo.review_call is None
    assert audit.records == []


@pytest.mark.asyncio
async def test_reject_with_comment_sets_reason() -> None:
    repo = _StubRepo(_pending())
    svc, audit, _ = _service(repo)
    result = await svc.review(
        listing_id=uuid4(), admin=_ADMIN, action="reject", comment="blurry title docs"
    )
    assert result.status == "rejected"
    assert repo.review_call == {"new_status": "rejected", "rejection_reason": "blurry title docs"}
    assert audit.records[0]["action"] == "listing.rejected"


@pytest.mark.asyncio
async def test_non_pending_listing_cannot_be_reviewed() -> None:
    repo = _StubRepo(OwnerStatus(seller_id=uuid4(), status="active", sale_type="normal"))
    svc, _, _ = _service(repo)
    with pytest.raises(NotPendingReview):
        await svc.review(listing_id=uuid4(), admin=_ADMIN, action="approve", comment=None)
    assert repo.review_call is None


@pytest.mark.asyncio
async def test_missing_listing_raises() -> None:
    svc, _, _ = _service(_StubRepo(None))
    with pytest.raises(ListingNotFound):
        await svc.review(listing_id=uuid4(), admin=_ADMIN, action="approve", comment=None)
