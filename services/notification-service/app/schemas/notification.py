"""Request/response models for the in-app notification centre (SCRUM-82)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.repositories.notification_repo import NotificationRow

# The inbox tabs (SCRUM-194). A Literal so an unknown tab is a 422 from FastAPI
# rather than a silently empty list, which would look like "you have nothing"
# instead of "that is not a tab".
#
# ⚠️ There is no "messages" category: this product has no messaging feature at
# all, so the design's Messages tab was dropped rather than shipped as a
# control that could never fill.
NotificationCategory = Literal["deposits", "bids", "documents", "system"]


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
