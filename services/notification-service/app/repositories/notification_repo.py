"""Access to the notifications table (owned by notification-service).

The in-app centre (SCRUM-82) reads a user's notifications newest-first with
keyset pagination and lets them mark items read. Every query is scoped to the
caller's user_id — a user can only ever see or mutate their own rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
                    WHERE user_id = :uid {keyset}
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
                text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid AND is_read = FALSE"),
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
