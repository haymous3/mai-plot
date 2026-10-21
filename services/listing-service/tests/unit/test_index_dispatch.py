"""Index dispatch — factory picks transport; enqueue never breaks the write."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.search_index import InMemorySearchIndex, PostgresSearchIndex
from app.services.index_dispatch import (
    CeleryIndexDispatcher,
    InlineIndexDispatcher,
    NullIndexDispatcher,
    build_index_dispatcher,
)


class _RecordingSync:
    def __init__(self) -> None:
        self.synced: list[UUID] = []

    async def sync_safe(self, listing_id: UUID) -> None:
        self.synced.append(listing_id)


def test_factory_picks_inline_for_dev_and_celery_for_prod() -> None:
    index = InMemorySearchIndex()
    inline = build_index_dispatcher(via_celery=False, index=index, listings=None)  # type: ignore[arg-type]
    celery = build_index_dispatcher(via_celery=True, index=index, listings=None)  # type: ignore[arg-type]
    assert isinstance(inline, InlineIndexDispatcher)
    assert isinstance(celery, CeleryIndexDispatcher)


def test_postgres_search_dispatches_nothing_whatever_the_transport() -> None:
    """SCRUM-251: under postgres search there is no second copy to sync, so
    even a prod config with index_via_celery=true must not enqueue tasks."""
    index = PostgresSearchIndex(listings=None)  # type: ignore[arg-type]
    for via_celery in (False, True):
        dispatcher = build_index_dispatcher(via_celery=via_celery, index=index, listings=None)  # type: ignore[arg-type]
        assert isinstance(dispatcher, NullIndexDispatcher)


@pytest.mark.asyncio
async def test_null_dispatch_is_a_no_op() -> None:
    await NullIndexDispatcher().enqueue(uuid4())  # must not raise or touch anything


@pytest.mark.asyncio
async def test_inline_dispatch_runs_sync_inline() -> None:
    rec = _RecordingSync()
    lid = uuid4()
    await InlineIndexDispatcher(sync=rec).enqueue(lid)  # type: ignore[arg-type]
    assert rec.synced == [lid]


@pytest.mark.asyncio
async def test_celery_enqueue_is_best_effort_when_broker_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broker failure on .delay() must be swallowed — indexing never fails
    the write (the listing stays in Postgres for a later reconcile)."""

    class _BoomTask:
        def delay(self, *args: object) -> None:
            raise RuntimeError("broker down")

    import app.tasks.listing_index as task_mod

    monkeypatch.setattr(task_mod, "sync_listing_index", _BoomTask())
    # Must not raise.
    await CeleryIndexDispatcher().enqueue(uuid4())
