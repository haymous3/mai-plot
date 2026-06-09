"""DB access for auth_credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthCredential


class AuthCredentialsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, *, user_id: UUID, password_hash: str) -> None:
        """Set (or replace) the password hash for a user."""
        existing = await self._session.get(AuthCredential, user_id)
        if existing is None:
            self._session.add(AuthCredential(user_id=user_id, password_hash=password_hash))
        else:
            existing.password_hash = password_hash
            existing.updated_at = datetime.now(UTC)
        await self._session.flush()

    async def get_password_hash(self, user_id: UUID) -> str | None:
        """Return the stored bcrypt hash, or None if the user has no password."""
        stmt = select(AuthCredential.password_hash).where(AuthCredential.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
