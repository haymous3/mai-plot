"""ListingIndexer.reindex_safe — best-effort, never raises."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.search_index import SearchDoc
from app.services.listing_indexer import ListingIndexer


class _StubRepo:
    def __init__(self, doc: SearchDoc | None) -> None:
        self._doc = doc

    async def get_search_doc(self, listing_id: UUID) -> SearchDoc | None:
        return self._doc


class _RecordingIndex:
    def __init__(self, *, fail: bool = False) -> None:
        self.upserted: list[SearchDoc] = []
        self.fail = fail

    async def upsert(self, doc: SearchDoc) -> None:
        if self.fail:
            raise RuntimeError("es down")
        self.upserted.append(doc)

    async def delete(self, listing_id: UUID) -> None: ...

    async def search(self, params: object) -> tuple[list[object], int]:
        return [], 0


def _doc() -> SearchDoc:
    from datetime import UTC, datetime

    return SearchDoc(
        id=uuid4(),
        title="t",
        description=None,
        property_type="land",
        state="Lagos",
        lga="Ikeja",
        address_text="a",
        lat=6.5,
        lng=3.4,
        size_sqm=None,
        asking_price_kobo=1,
        sale_type="normal",
        urgency_tag=None,
        expires_at=None,
        status="active",
        doc_verification_status="not_submitted",
        seller_authority_type="owner",
        view_count=0,
        interest_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_reindex_upserts_when_doc_found() -> None:
    doc = _doc()
    index = _RecordingIndex()
    indexer = ListingIndexer(index=index, listings=_StubRepo(doc))  # type: ignore[arg-type]
    await indexer.reindex_safe(doc.id)
    assert index.upserted == [doc]


@pytest.mark.asyncio
async def test_reindex_noop_when_doc_missing() -> None:
    index = _RecordingIndex()
    indexer = ListingIndexer(index=index, listings=_StubRepo(None))  # type: ignore[arg-type]
    await indexer.reindex_safe(uuid4())
    assert index.upserted == []


@pytest.mark.asyncio
async def test_reindex_swallows_index_failure() -> None:
    # An index failure must NOT propagate — the DB write already succeeded.
    index = _RecordingIndex(fail=True)
    indexer = ListingIndexer(index=index, listings=_StubRepo(_doc()))  # type: ignore[arg-type]
    await indexer.reindex_safe(uuid4())  # no raise
