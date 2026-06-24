"""Read-only access to user contact data (SCRUM-80).

The `users` / `user_pii` tables are owned by auth-service; notification-service
reads them read-only over the shared DB (same cross-service pattern listing- and
transaction-service use) to resolve the recipient's phone for an SMS send. When
the databases are split this becomes a REST call to auth-service — the seam is
this one method.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_phone(self, user_id: UUID) -> str | None:
        """The user's stored phone, or None if the user (or their PII row) is
        absent or soft-deleted. The raw string is returned as-stored; the SMS
        path normalises it to E.164 before dialling."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT p.phone
                    FROM user_pii p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.user_id = :uid AND u.deleted_at IS NULL
                    """
                ),
                {"uid": user_id},
            )
        ).first()
        return row.phone if row is not None else None

    async def get_email(self, user_id: UUID) -> str | None:
        """The user's email, or None if absent/soft-deleted or never set (email
        is nullable — phone-only registrations have none)."""
        row = (
            await self._session.execute(
                text("SELECT email FROM users WHERE id = :uid AND deleted_at IS NULL"),
                {"uid": user_id},
            )
        ).first()
        return row.email if row is not None else None
