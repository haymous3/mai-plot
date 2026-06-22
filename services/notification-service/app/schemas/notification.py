"""Request/response models for the in-app notification centre (SCRUM-82)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.notification_repo import NotificationRow


class NotificationItem(BaseModel):
    id: UUID
    channel: str
    type: str
    title: str | None
    body: str
    reference_type: str | None
    reference_id: UUID | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def from_row(cls, row: NotificationRow) -> NotificationItem:
        return cls(
            id=row.id,
            channel=row.channel,
            type=row.type,
            title=row.title,
            body=row.body,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            is_read=row.is_read,
            created_at=row.created_at,
            read_at=row.read_at,
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    next_cursor: str | None
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked_read: int
