"""Append-only writes to audit_log.

Repository layer per CLAUDE.md §4 — services call `record()`, never touch
the ORM directly. There is deliberately no update/delete: the audit trail
is INSERT-only (data-model.md §19).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


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
        """Insert one audit row inside the caller's transaction.

        The route's get_session dependency owns the commit; this only adds
        the row so it lands atomically with the state change it records.
        """
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
