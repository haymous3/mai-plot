"""Read access to audit_log (owned by analytics-service, created in migration
0001). Every other service writes here (INSERT-only); analytics-service is the
read side — this powers the admin audit-log viewer (SCRUM-126).

Read-only: SELECTs with optional entity/actor/action/date filters, newest-first,
offset-paginated. The idx_audit_entity (entity_type, entity_id, created_at DESC)
and idx_audit_actor (actor_id, created_at DESC) indexes cover the filtered paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AuditLogRow:
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


@dataclass(frozen=True)
class AuditQuery:
    entity_type: str | None = None
    entity_id: UUID | None = None
    actor_id: UUID | None = None
    action: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


# ip_address is INET — cast to text so it serializes as a plain string. JSONB
# old_value/new_value decode to dicts via the asyncpg driver.
_COLUMNS = (
    "id, actor_id, actor_role, action, entity_type, entity_id, old_value, "
    "new_value, ip_address::text AS ip_address, user_agent, created_at"
)


class AuditLogReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _where(query: AuditQuery) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if query.entity_type is not None:
            clauses.append("entity_type = :entity_type")
            params["entity_type"] = query.entity_type
        if query.entity_id is not None:
            clauses.append("entity_id = :entity_id")
            params["entity_id"] = query.entity_id
        if query.actor_id is not None:
            clauses.append("actor_id = :actor_id")
            params["actor_id"] = query.actor_id
        if query.action is not None:
            clauses.append("action = :action")
            params["action"] = query.action
        if query.date_from is not None:
            clauses.append("created_at >= :date_from")
            params["date_from"] = query.date_from
        if query.date_to is not None:
            clauses.append("created_at <= :date_to")
            params["date_to"] = query.date_to
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    async def count(self, query: AuditQuery) -> int:
        where, params = self._where(query)
        total = (
            await self._session.execute(text(f"SELECT COUNT(*) FROM audit_log{where}"), params)
        ).scalar_one()
        return int(total)

    async def list(self, query: AuditQuery, *, limit: int, offset: int) -> list[AuditLogRow]:
        where, params = self._where(query)
        rows = (
            await self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM audit_log{where} "
                    "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": limit, "offset": offset},
            )
        ).all()
        return [self._to_row(r) for r in rows]

    @staticmethod
    def _to_row(r: Any) -> AuditLogRow:
        return AuditLogRow(
            id=r.id,
            actor_id=r.actor_id,
            actor_role=r.actor_role,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            old_value=r.old_value,
            new_value=r.new_value,
            ip_address=r.ip_address,
            user_agent=r.user_agent,
            created_at=r.created_at,
        )
