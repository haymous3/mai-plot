"""Access to the notifications table (owned by notification-service).

The in-app centre (SCRUM-82) reads a user's notifications newest-first with
keyset pagination and lets them mark items read. Every query is scoped to the
caller's user_id — a user can only ever see or mutate their own rows. The centre
shows only `channel = 'in_app'` rows: the table holds one row per delivery
attempt per channel (SCRUM-80 adds 'sms' rows alongside), so the in-app feed
filters to its own channel rather than surfacing every SMS/email delivery twice.

`create` / `get_by_id` / `mark_sent` (SCRUM-80) support the dispatch path: a
notification is written once, then a channel send (e.g. SMS) stamps sent_at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import categories
from app.services.cursor import Cursor


@dataclass(frozen=True)
class NotificationRow:
    id: UUID
    user_id: UUID
    channel: str
    type: str
    title: str | None
    body: str
    reference_type: str | None
    reference_id: UUID | None
    is_read: bool
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime


# Escape character for the inbox search's ILIKE (SCRUM-194). Not a backslash:
# see the comment at the call site for why.
_LIKE_ESCAPE = "!"


def _escape_like(value: str) -> str:
    """Neutralise LIKE wildcards in a user's search term.

    The escape character itself goes first — escaping `%` before `!` would
    double-escape the `!` introduced by that very step.
    """
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _category_clause(
        category: str | None, params: dict[str, object]
    ) -> tuple[dict[str, object], str]:
        """SQL for the category tab, plus the params it needs.

        SYSTEM is the catch-all — an unmapped type belongs to it — so it cannot
        be expressed as an inclusion list. It is the COMPLEMENT of every type
        claimed by another tab, which also means a brand-new notification type
        shows up under System without anyone editing this.

        The type lists are interpolated as a bound `IN` via `ANY(:types)`
        rather than string-joined into the SQL: they come from a closed
        in-process mapping, but building SQL by concatenation is the habit that
        eventually meets a value that did not come from there.
        """
        if category is None:
            return params, ""
        if category == categories.SYSTEM:
            params["types"] = categories.types_outside_system()
            return params, "AND NOT (type = ANY(:types))"
        params["types"] = categories.types_in(category)
        return params, "AND type = ANY(:types)"

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        after: Cursor | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> list[NotificationRow]:
        """Newest-first page of a user's notifications. `after` resumes strictly
        after a previously-seen (created_at, id) pair via keyset comparison.
        Callers ask for limit+1 to detect whether another page exists.

        `category` and `query` narrow the same feed for the inbox tabs and its
        search box (SCRUM-194). Both are applied in SQL rather than after the
        fetch: filtering a page that has already been cut to `limit` would
        return short pages and break the keyset cursor, which assumes the rows
        it skips past are the rows the caller actually saw."""
        params: dict[str, object] = {"uid": user_id, "lim": limit}
        keyset = ""
        if after is not None:
            keyset = "AND (created_at, id) < (:cc, :ci)"
            params["cc"] = after.created_at
            params["ci"] = after.id

        params, category_clause = self._category_clause(category, params)

        search = ""
        if query:
            # ILIKE over title+body, with the user's own wildcards neutralised:
            # an unescaped `%` or `_` would silently WIDEN their search to match
            # rows they did not ask for, which is worse than matching none.
            #
            # `!` is the escape character rather than the conventional
            # backslash, deliberately. A backslash has to survive a Python
            # string literal AND Postgres's own string parsing, and getting it
            # wrong is quiet: the first attempt here compiled to `ESCAPE ''`
            # and a literal `\%`, which the tests below caught. `!` has no
            # special meaning to either layer.
            search = (
                f"AND (COALESCE(title, '') ILIKE :q ESCAPE '{_LIKE_ESCAPE}' "
                f"OR body ILIKE :q ESCAPE '{_LIKE_ESCAPE}')"
            )
            params["q"] = f"%{_escape_like(query)}%"

        rows = (
            await self._session.execute(
                text(
                    f"""
                    SELECT id, user_id, channel, type, title, body, reference_type,
                           reference_id, is_read, sent_at, read_at, created_at
                    FROM notifications
                    WHERE user_id = :uid AND channel = 'in_app'
                          AND archived_at IS NULL {keyset} {category_clause} {search}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :lim
                    """
                ),
                params,
            )
        ).all()
        return [
            NotificationRow(
                id=r.id,
                user_id=r.user_id,
                channel=r.channel,
                type=r.type,
                title=r.title,
                body=r.body,
                reference_type=r.reference_type,
                reference_id=r.reference_id,
                is_read=r.is_read,
                sent_at=r.sent_at,
                read_at=r.read_at,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def unread_count(self, user_id: UUID) -> int:
        count = (
            await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM notifications "
                    "WHERE user_id = :uid AND channel = 'in_app' "
                    "AND is_read = FALSE AND archived_at IS NULL"
                ),
                {"uid": user_id},
            )
        ).scalar_one()
        assert isinstance(count, int)
        return count

    async def mark_read(self, notification_id: UUID, *, user_id: UUID) -> bool:
        """Mark one notification read. Scoped to the owner, so another user's id
        returns False (the route maps that to 404). Idempotent — read_at is set
        once and preserved via COALESCE on a re-mark."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE notifications SET is_read = TRUE, read_at = COALESCE(read_at, NOW()) "
                    "WHERE id = :id AND user_id = :uid RETURNING id"
                ),
                {"id": notification_id, "uid": user_id},
            )
        ).first()
        return row is not None

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all of a user's unread notifications read; returns how many were
        flipped (0 if already all read)."""
        rows = (
            await self._session.execute(
                text(
                    "UPDATE notifications SET is_read = TRUE, read_at = COALESCE(read_at, NOW()) "
                    "WHERE user_id = :uid AND is_read = FALSE RETURNING id"
                ),
                {"uid": user_id},
            )
        ).all()
        return len(rows)

    async def archive_older_than(self, *, days: int, limit: int = 5000) -> int:
        """Stamp archived_at on live notifications older than `days`, up to
        `limit` per call (SCRUM-120). Returns how many were archived. Idempotent:
        already-archived rows are excluded, so re-running never re-touches them."""
        rows = (
            await self._session.execute(
                text(
                    """
                    WITH old AS (
                        SELECT id FROM notifications
                        WHERE archived_at IS NULL
                          AND created_at < NOW() - make_interval(days => :days)
                        ORDER BY created_at
                        LIMIT :limit
                    )
                    UPDATE notifications SET archived_at = NOW()
                    WHERE id IN (SELECT id FROM old)
                    RETURNING id
                    """
                ),
                {"days": days, "limit": limit},
            )
        ).all()
        return len(rows)

    async def create(
        self,
        *,
        user_id: UUID,
        channel: str,
        type: str,
        body: str,
        title: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        sent_now: bool = False,
    ) -> NotificationRow:
        """Insert one notification row and return it. `sent_now` stamps sent_at
        at insert (used for in_app rows, which are delivered to the centre the
        moment they exist); channels with an external send (sms) leave sent_at
        NULL until the send confirms."""
        sent_at_value = "NOW()" if sent_now else "NULL"
        row = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO notifications
                        (user_id, channel, type, title, body, reference_type,
                         reference_id, sent_at)
                    VALUES
                        (:uid, :channel, :type, :title, :body, :reference_type,
                         :reference_id, {sent_at_value})
                    RETURNING id, user_id, channel, type, title, body, reference_type,
                              reference_id, is_read, sent_at, read_at, created_at
                    """
                ),
                {
                    "uid": user_id,
                    "channel": channel,
                    "type": type,
                    "title": title,
                    "body": body,
                    "reference_type": reference_type,
                    "reference_id": reference_id,
                },
            )
        ).one()
        return self._to_row(row)

    async def get_by_id(self, notification_id: UUID) -> NotificationRow | None:
        """Load one notification by id, unscoped — the SMS send task holds the id
        and needs the row regardless of caller (there is no caller)."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id, user_id, channel, type, title, body, reference_type,
                           reference_id, is_read, sent_at, read_at, created_at
                    FROM notifications
                    WHERE id = :id
                    """
                ),
                {"id": notification_id},
            )
        ).first()
        return self._to_row(row) if row is not None else None

    async def mark_sent(self, notification_id: UUID) -> bool:
        """Stamp sent_at on a successful channel send. Idempotent (COALESCE keeps
        the first send time); returns False if the id no longer exists."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE notifications SET sent_at = COALESCE(sent_at, NOW()) "
                    "WHERE id = :id RETURNING id"
                ),
                {"id": notification_id},
            )
        ).first()
        return row is not None

    @staticmethod
    def _to_row(r: Any) -> NotificationRow:
        return NotificationRow(
            id=r.id,
            user_id=r.user_id,
            channel=r.channel,
            type=r.type,
            title=r.title,
            body=r.body,
            reference_type=r.reference_type,
            reference_id=r.reference_id,
            is_read=r.is_read,
            sent_at=r.sent_at,
            read_at=r.read_at,
            created_at=r.created_at,
        )
