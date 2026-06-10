"""ListingQueryService feed shaping + cache key (redis=None path)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.repositories.listing_repo import FeedFilters, FeedRow
from app.services.listing_query import ListingQueryService, _cache_key


def _row(**overrides: object) -> FeedRow:
    base: dict[str, object] = {
        "id": uuid4(),
        "title": "Plot A",
        "property_type": "land",
        "state": "Lagos",
        "lga": "Ikeja",
        "size_sqm": Decimal("500.00"),
        "asking_price_kobo": 5_000_000_000,
        "sale_type": "distress",
        "urgency_tag": "7_days",
        "expires_at": datetime(2026, 6, 20, tzinfo=UTC),
        "status": "active",
        "doc_verification_status": "verified",
        "view_count": 3,
        "interest_count": 1,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC),
        "seller_authority_type": "owner",
    }
    base.update(overrides)
    return FeedRow(**base)  # type: ignore[arg-type]


class _StubRepo:
    def __init__(self, rows: list[FeedRow], total: int) -> None:
        self._rows = rows
        self._total = total
        self.calls = 0

    async def list_feed(self, filters: FeedFilters) -> tuple[list[FeedRow], int]:
        self.calls += 1
        return self._rows, self._total


def _service(repo: _StubRepo) -> ListingQueryService:
    return ListingQueryService(redis=None, listings=repo, ttl_seconds=60)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_feed_maps_rows_and_pagination() -> None:
    repo = _StubRepo([_row(), _row()], total=42)
    result = await _service(repo).get_feed(FeedFilters(page=2, page_size=20))

    assert len(result.data) == 2
    item = result.data[0]
    assert item.urgency_expires_at == datetime(2026, 6, 20, tzinfo=UTC)
    assert item.thumbnail_url is None  # media upload not built yet
    assert item.seller_authority_type == "owner"
    assert result.pagination.page == 2
    assert result.pagination.total == 42
    assert result.pagination.total_pages == 3  # ceil(42/20)


@pytest.mark.asyncio
async def test_empty_feed_has_zero_pages() -> None:
    result = await _service(_StubRepo([], total=0)).get_feed(FeedFilters())
    assert result.data == []
    assert result.pagination.total_pages == 0


def test_cache_key_is_stable_and_filter_sensitive() -> None:
    a = FeedFilters(state="Lagos", page=1)
    b = FeedFilters(state="Lagos", page=1)
    c = FeedFilters(state="Lagos", page=2)
    assert _cache_key(a) == _cache_key(b)
    assert _cache_key(a) != _cache_key(c)
    assert _cache_key(a).startswith("feed:")
