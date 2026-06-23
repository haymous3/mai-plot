"""Access to push_subscriptions (owned by notification-service, SCRUM-79).

One row per (user, browser endpoint). Registration upserts on (user_id,
endpoint) and revives a soft-deleted row; a push that hits a dead subscription
soft-deletes it. Every read is scoped to a single user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PushSubscriptionRow:
    id: UUID
    user_id: UUID
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class PushSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str | None = None,
    ) -> UUID:
        """Register (or refresh) a subscription. A repeat (user, endpoint) updates
        the keys and revives it if it had been soft-deleted; returns the row id."""
        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO push_subscriptions
                        (user_id, endpoint, p256dh, auth, user_agent)
                    VALUES (:uid, :endpoint, :p256dh, :auth, :ua)
                    ON CONFLICT (user_id, endpoint) DO UPDATE
                        SET p256dh = EXCLUDED.p256dh,
                            auth = EXCLUDED.auth,
                            user_agent = EXCLUDED.user_agent,
                            deleted_at = NULL,
                            updated_at = NOW()
                    RETURNING id
                    """
                ),
                {
                    "uid": user_id,
                    "endpoint": endpoint,
                    "p256dh": p256dh,
                    "auth": auth,
                    "ua": user_agent,
                },
            )
        ).one()
        result: UUID = row.id
        return result

    async def list_active_for_user(self, user_id: UUID) -> list[PushSubscriptionRow]:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, user_id, endpoint, p256dh, auth, user_agent,
                           created_at, updated_at, deleted_at
                    FROM push_subscriptions
                    WHERE user_id = :uid AND deleted_at IS NULL
                    ORDER BY created_at
                    """
                ),
                {"uid": user_id},
            )
        ).all()
        return [self._to_row(r) for r in rows]

    async def soft_delete(self, subscription_id: UUID) -> bool:
        """Soft-delete by id — used when a push reveals the subscription is dead.
        Idempotent; returns False if already deleted or absent."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE push_subscriptions SET deleted_at = NOW() "
                    "WHERE id = :id AND deleted_at IS NULL RETURNING id"
                ),
                {"id": subscription_id},
            )
        ).first()
        return row is not None

    async def soft_delete_by_endpoint(self, *, user_id: UUID, endpoint: str) -> bool:
        """Unsubscribe — scoped to the caller, so a foreign endpoint is a no-op
        (False, which the route maps to 404)."""
        row = (
            await self._session.execute(
                text(
                    "UPDATE push_subscriptions SET deleted_at = NOW() "
                    "WHERE user_id = :uid AND endpoint = :endpoint AND deleted_at IS NULL "
                    "RETURNING id"
                ),
                {"uid": user_id, "endpoint": endpoint},
            )
        ).first()
        return row is not None

    @staticmethod
    def _to_row(r: Any) -> PushSubscriptionRow:
        return PushSubscriptionRow(
            id=r.id,
            user_id=r.user_id,
            endpoint=r.endpoint,
            p256dh=r.p256dh,
            auth=r.auth,
            user_agent=r.user_agent,
            created_at=r.created_at,
            updated_at=r.updated_at,
            deleted_at=r.deleted_at,
        )
