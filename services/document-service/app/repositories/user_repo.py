"""Cross-service read of a user's display name from the shared user_pii table.

The buyer's name (for the watermark overlay) lives in auth-service's
`user_pii`. document-service reads it directly — the database is shared
(consistent with the other services' cross-service reads). Read-only.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_display_name(self, user_id: UUID) -> str | None:
        """The user's full_name if set and non-empty, else None."""
        name = (
            await self._session.execute(
                text("SELECT full_name FROM user_pii WHERE user_id = :id"),
                {"id": user_id},
            )
        ).scalar_one_or_none()
        if name is None or not str(name).strip():
            return None
        return str(name)
