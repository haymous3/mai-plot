"""Unit tests for NotificationCentreService with a stubbed repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.notification_repo import NotificationRow
from app.services.cursor import Cursor, decode_cursor
from app.services.notification_centre import NotificationCentreService, NotificationNotFound


class _StubNotifRepo:
    def __init__(self, rows: list[NotificationRow], *, unread: int = 0) -> None:
        self._rows = rows
        self._unread = unread
        self.mark_read_result = True
        self.mark_all_result = 0
        self.last_after: Cursor | None = None
        self.last_category: str | None = None
        self.last_query: str | None = None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        after: Cursor | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> list[NotificationRow]:
        self.last_after = after
        self.last_category = category
        self.last_query = query
        return self._rows[:limit]

    async def unread_count(self, user_id: UUID) -> int:
        return self._unread

    async def mark_read(self, notification_id: UUID, *, user_id: UUID) -> bool:
        return self.mark_read_result

    async def mark_all_read(self, user_id: UUID) -> int:
        return self.mark_all_result


def _row(created: datetime, *, ident: UUID | None = None) -> NotificationRow:
    return NotificationRow(
        id=ident or uuid4(),
        user_id=uuid4(),
        channel="in_app",
        type="offer_accepted",
        title="Offer accepted",
        body="Your offer was accepted.",
        reference_type=None,
        reference_id=None,
        is_read=False,
        sent_at=None,
        read_at=None,
        created_at=created,
    )


def _service(repo: _StubNotifRepo) -> NotificationCentreService:
    return NotificationCentreService(notifications=repo)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_list_returns_no_cursor_when_page_not_full() -> None:
    rows = [_row(datetime(2026, 6, 1, tzinfo=UTC))]
    repo = _StubNotifRepo(rows, unread=1)
    page = await _service(repo).list_notifications(uuid4(), limit=20)
    assert page.next_cursor is None
    assert page.unread_count == 1
    assert len(page.items) == 1


@pytest.mark.asyncio
async def test_list_emits_cursor_when_more_rows_exist() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)
    last_id = uuid4()
    # 3 rows but limit 2 — repo is asked for limit+1 (3) and returns all 3,
    # so the service trims to 2 and emits a cursor pointing at the 2nd row.
    rows = [
        _row(now, ident=uuid4()),
        _row(now - timedelta(minutes=1), ident=last_id),
        _row(now - timedelta(minutes=2), ident=uuid4()),
    ]
    repo = _StubNotifRepo(rows, unread=3)
    page = await _service(repo).list_notifications(uuid4(), limit=2)
    assert len(page.items) == 2
    assert page.next_cursor is not None
    decoded = decode_cursor(page.next_cursor)
    assert decoded.id == last_id


@pytest.mark.asyncio
async def test_list_passes_decoded_cursor_to_repo() -> None:
    from app.services.cursor import encode_cursor

    created = datetime(2026, 5, 1, tzinfo=UTC)
    ident = uuid4()
    repo = _StubNotifRepo([], unread=0)
    await _service(repo).list_notifications(uuid4(), limit=20, cursor=encode_cursor(created, ident))
    assert repo.last_after is not None
    assert repo.last_after.id == ident


@pytest.mark.asyncio
async def test_mark_read_raises_when_not_owned() -> None:
    repo = _StubNotifRepo([])
    repo.mark_read_result = False
    with pytest.raises(NotificationNotFound):
        await _service(repo).mark_read(uuid4(), user_id=uuid4())


@pytest.mark.asyncio
async def test_mark_all_read_returns_count() -> None:
    repo = _StubNotifRepo([])
    repo.mark_all_result = 4
    assert await _service(repo).mark_all_read(uuid4()) == 4


# --------------------------------------------------------------------------
# SCRUM-194 — the filters reach the repository, and the badge does not move
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_and_query_are_passed_through_to_the_repository() -> None:
    repo = _StubNotifRepo([])
    page = await _service(repo).list_notifications(
        uuid4(), limit=10, category="bids", query="lekki"
    )

    assert repo.last_category == "bids"
    assert repo.last_query == "lekki"
    assert page.items == []


@pytest.mark.asyncio
async def test_no_filters_reach_the_repository_as_none() -> None:
    """ "All", with an empty search box, must not become a filter."""
    repo = _StubNotifRepo([])
    await _service(repo).list_notifications(uuid4(), limit=10)

    assert repo.last_category is None
    assert repo.last_query is None


@pytest.mark.asyncio
async def test_unread_count_is_the_whole_inbox_not_the_filtered_tab() -> None:
    """The badge means "unread everywhere". If it tracked the open tab it would
    be saying something false about the rest of the inbox."""
    repo = _StubNotifRepo([], unread=7)
    page = await _service(repo).list_notifications(uuid4(), limit=10, category="bids")

    assert page.items == []
    assert page.unread_count == 7
