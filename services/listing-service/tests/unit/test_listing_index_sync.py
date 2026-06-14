"""ListingIndexSync — upsert vs remove, es_indexed_at stamp, raise vs swallow."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.adapters.search_index import InMemorySearchIndex, SearchDoc
from app.services.listing_index_sync import ListingIndexSync


def _doc(listing_id: UUID, *, status: str = "active") -> SearchDoc:
    return SearchDoc(
        id=listing_id,
        title="Lekki Plot",
        description=None,
        property_type="land",
        state="Lagos",
        lga="Eti-Osa",
        address_text="1 Admiralty Way",
        lat=6.4281,
        lng=3.4219,
        size_sqm=Decimal("500.00"),
        asking_price_kobo=5_000_000_000,
        sale_type="normal",
        urgency_tag=None,
        expires_at=datetime(2026, 9, 1, tzinfo=UTC),
        status=status,
        doc_verification_status="verified",
        seller_authority_type="owner",
        view_count=0,
        interest_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


class _StubRepo:
    """get_search_doc returns a preset doc (or None); records es_indexed stamps."""

    def __init__(self, doc: SearchDoc | None) -> None:
        self._doc = doc
        self.stamped: list[UUID] = []

    async def get_search_doc(self, listing_id: UUID) -> SearchDoc | None:
        return self._doc

    async def mark_es_indexed(self, listing_id: UUID) -> None:
        self.stamped.append(listing_id)


class _FailingIndex(InMemorySearchIndex):
    async def upsert(self, doc: SearchDoc) -> None:
        raise RuntimeError("es down")


@pytest.mark.asyncio
async def test_active_listing_is_upserted_and_stamped() -> None:
    lid = uuid4()
    index = InMemorySearchIndex()
    repo = _StubRepo(_doc(lid, status="active"))

    action = await ListingIndexSync(index=index, listings=repo).sync(lid)  # type: ignore[arg-type]

    assert action == "upserted"
    assert lid in index.docs  # type: ignore[operator]
    assert repo.stamped == [lid]  # es_indexed_at updated after sync


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["expired", "rejected", "cancelled", "sold"])
async def test_terminal_status_is_removed_from_index(status: str) -> None:
    lid = uuid4()
    index = InMemorySearchIndex()
    await index.upsert(_doc(lid, status="active"))  # previously indexed
    repo = _StubRepo(_doc(lid, status=status))

    action = await ListingIndexSync(index=index, listings=repo).sync(lid)  # type: ignore[arg-type]

    assert action == "deleted"
    assert lid not in index.docs  # type: ignore[operator]
    assert repo.stamped == [lid]


@pytest.mark.asyncio
async def test_deleted_listing_no_live_row_is_removed() -> None:
    lid = uuid4()
    index = InMemorySearchIndex()
    await index.upsert(_doc(lid, status="active"))
    repo = _StubRepo(None)  # get_search_doc returns None for a soft-deleted row

    action = await ListingIndexSync(index=index, listings=repo).sync(lid)  # type: ignore[arg-type]

    assert action == "deleted"
    assert lid not in index.docs  # type: ignore[operator]


@pytest.mark.asyncio
async def test_sync_raises_on_index_failure() -> None:
    """sync() must propagate so the Celery task retries (no es_indexed stamp)."""
    lid = uuid4()
    repo = _StubRepo(_doc(lid, status="active"))

    with pytest.raises(RuntimeError):
        await ListingIndexSync(index=_FailingIndex(), listings=repo).sync(lid)  # type: ignore[arg-type]
    assert repo.stamped == []  # not stamped on failure


@pytest.mark.asyncio
async def test_sync_safe_swallows_failure() -> None:
    lid = uuid4()
    repo = _StubRepo(_doc(lid, status="active"))

    # Must not raise — best-effort path for inline dispatch / batch jobs.
    await ListingIndexSync(index=_FailingIndex(), listings=repo).sync_safe(lid)  # type: ignore[arg-type]
    assert repo.stamped == []
