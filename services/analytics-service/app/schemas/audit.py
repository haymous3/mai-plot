"""Response schemas for the admin audit-log viewer (SCRUM-126)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.repositories.audit_repo import AuditLogRow


class AuditLogItem(BaseModel):
    id: UUID
    actor_id: UUID | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: AuditLogRow) -> AuditLogItem:
        return cls(
            id=row.id,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            old_value=row.old_value,
            new_value=row.new_value,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at,
        )


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    pagination: Pagination
