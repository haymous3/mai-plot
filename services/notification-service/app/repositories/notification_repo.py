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


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        after: Cursor | None = None,
    ) -> list[NotificationRow]:
        """Newest-first page of a user's notifications. `after` resumes strictly
        after a previously-seen (created_at, id) pair via keyset comparison.
        Callers ask for limit+1 to detect whether another page exists."""
        params: dict[str, object] = {"uid": user_id, "lim": limit}
        keyset = ""
        if after is not None:
            keyset = "AND (created_at, id) < (:cc, :ci)"
            params["cc"] = after.created_at
            params["ci"] = after.id
        rows = (
            await self._session.execute(
                text(
                    f"""
                    SELECT id, user_id, channel, type, title, body, reference_type,
                           reference_id, is_read, sent_at, read_at, created_at
                    FROM notifications
                    WHERE user_id = :uid AND channel = 'in_app' {keyset}
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
                    "WHERE user_id = :uid AND channel = 'in_app' AND is_read = FALSE"
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
