"""The shared audit_log (data-model.md §19): append-only writes, plus one
entity-scoped read.

INSERT-only — the trail is never updated or deleted; the table has DB triggers
that block UPDATE and DELETE outright. Listing state changes (admin
approve/reject/pause/take-down) record a row so the transition is traceable.

The read (SCRUM-215) exists because "what happened to this listing, and who did
it" is the question an admin opening a property actually has, and the answer was
only reachable through analytics-service's global audit browser — which means
knowing the listing id and then filtering a firehose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


@dataclass(frozen=True)
class AuditEntry:
    """One recorded state change on an entity."""

    id: UUID
    actor_id: UUID | None
    actor_role: str | None
    action: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        actor_id: UUID | None,
        actor_role: str | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        old_value: dict[str, object] | None = None,
        new_value: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Insert one audit row inside the caller's transaction (committed by
        the route's get_session dependency, atomically with the state change)."""
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self._session.flush()

    async def list_for_entity(
        self, *, entity_type: str, entity_id: UUID, limit: int = 50
    ) -> list[AuditEntry]:
        """This entity's recorded state changes, newest first (SCRUM-215).

        Capped rather than paginated: a listing accumulates a handful of
        transitions over its life, and an admin reading a history wants the
        recent end of it. If one ever grows past the cap, that is itself worth
        seeing in the global audit browser.
        """
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, actor_id, actor_role, action, old_value, new_value, created_at
                    FROM audit_log
                    WHERE entity_type = :etype AND entity_id = :eid
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"etype": entity_type, "eid": entity_id, "limit": limit},
            )
        ).all()
        return [
            AuditEntry(
                id=r.id,
                actor_id=r.actor_id,
                actor_role=r.actor_role,
                action=r.action,
                old_value=r.old_value,
                new_value=r.new_value,
                created_at=r.created_at,
            )
            for r in rows
        ]
