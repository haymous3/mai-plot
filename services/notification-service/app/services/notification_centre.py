"""In-app notification centre service (SCRUM-82).

Orchestrates the notifications repository: lists a user's feed with keyset
pagination + unread count, and marks items read. No external providers — the
in-app channel is just the persisted row; push/SMS/email delivery are separate
stories (SCRUM-79/80/81).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.notification_repo import NotificationRepository, NotificationRow
from app.services.cursor import Cursor, decode_cursor, encode_cursor


class NotificationNotFound(RuntimeError):
    """The notification does not exist, or does not belong to the caller."""


@dataclass(frozen=True)
class NotificationPage:
    items: list[NotificationRow]
    next_cursor: str | None
    unread_count: int


class NotificationCentreService:
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def list_notifications(
        self,
        user_id: UUID,
        *,
        limit: int,
        cursor: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> NotificationPage:
        """One page of the caller's feed plus their live unread count. Decoding
        the cursor is the caller's concern only in that a bad one raises
        CursorInvalid (mapped to 400 at the route).

        `category` and `query` narrow the feed for the inbox tabs and search
        (SCRUM-194). ⚠️ `unread_count` is deliberately NOT narrowed with them:
        it drives the badge, which has to mean "unread everywhere" — a badge
        that shrank when you opened a tab would be telling you something false
        about the rest of the inbox."""
        after: Cursor | None = decode_cursor(cursor) if cursor else None
        # Over-fetch by one to learn whether a further page exists without a
        # second COUNT query.
        rows = await self._notifications.list_for_user(
            user_id, limit=limit + 1, after=after, category=category, query=query
        )
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        unread = await self._notifications.unread_count(user_id)
        return NotificationPage(items=rows, next_cursor=next_cursor, unread_count=unread)

    async def mark_read(self, notification_id: UUID, *, user_id: UUID) -> None:
        updated = await self._notifications.mark_read(notification_id, user_id=user_id)
        if not updated:
            raise NotificationNotFound()

    async def mark_all_read(self, user_id: UUID) -> int:
        return await self._notifications.mark_all_read(user_id)
