"""view_count dispatch — factory picks transport; enqueue never breaks the read."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.view_count_dispatch import (
    CeleryViewCountDispatcher,
    InlineViewCountDispatcher,
    build_view_count_dispatcher,
)


class _RecordingRepo:
    def __init__(self, *, fail: bool = False) -> None:
        self.incremented: list[UUID] = []
        self._fail = fail

    async def increment_view_count(self, listing_id: UUID) -> None:
        if self._fail:
            raise RuntimeError("db down")
        self.incremented.append(listing_id)


def test_factory_picks_inline_for_dev_and_celery_for_prod() -> None:
    repo = _RecordingRepo()
    inline = build_view_count_dispatcher(via_celery=False, listings=repo)  # type: ignore[arg-type]
    celery = build_view_count_dispatcher(via_celery=True, listings=repo)  # type: ignore[arg-type]
    assert isinstance(inline, InlineViewCountDispatcher)
    assert isinstance(celery, CeleryViewCountDispatcher)


@pytest.mark.asyncio
async def test_inline_dispatch_increments_via_repo() -> None:
    repo = _RecordingRepo()
    lid = uuid4()
    await InlineViewCountDispatcher(listings=repo).enqueue(lid)  # type: ignore[arg-type]
    assert repo.incremented == [lid]


@pytest.mark.asyncio
async def test_inline_dispatch_is_best_effort() -> None:
    repo = _RecordingRepo(fail=True)
    # A DB error must be swallowed — view-counting never breaks the read.
    await InlineViewCountDispatcher(listings=repo).enqueue(uuid4())  # type: ignore[arg-type]
    assert repo.incremented == []


@pytest.mark.asyncio
async def test_celery_enqueue_is_best_effort_when_broker_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomTask:
        def delay(self, *args: object) -> None:
            raise RuntimeError("broker down")

    import app.tasks.view_count as task_mod

    monkeypatch.setattr(task_mod, "increment_view_count", _BoomTask())
    # Must not raise.
    await CeleryViewCountDispatcher().enqueue(uuid4())
