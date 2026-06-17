"""Append-only writes to audit_log (owned by analytics-service).

transaction-service does not own or migrate audit_log — it only INSERTs, the
shared-DB pattern used by the other services. Every transaction state change is
recorded here (SCRUM-67) in addition to the transaction_events log.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
        await self._session.execute(
            text(
                """
                INSERT INTO audit_log
                    (actor_id, actor_role, action, entity_type, entity_id,
                     old_value, new_value, ip_address, user_agent)
                VALUES
                    (:actor_id, :actor_role, :action, :entity_type, :entity_id,
                     CAST(:old AS jsonb), CAST(:new AS jsonb), :ip, :ua)
                """
            ),
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old": json.dumps(old_value) if old_value is not None else None,
                "new": json.dumps(new_value) if new_value is not None else None,
                "ip": ip_address,
                "ua": user_agent,
            },
        )
