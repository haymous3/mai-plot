"""DB access for refresh_tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


@dataclass(frozen=True)
class StoredRefreshToken:
    """View struct — keeps the ORM row out of the service layer."""

    id: UUID
    user_id: UUID
    expires_at: datetime
    revoked_at: datetime | None


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: UUID, token_hash: str, expires_at: datetime) -> UUID:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token.id

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        stmt = select(
            RefreshToken.id,
            RefreshToken.user_id,
            RefreshToken.expires_at,
            RefreshToken.revoked_at,
        ).where(RefreshToken.token_hash == token_hash)
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        revoked_at = row.revoked_at
        if revoked_at is not None and revoked_at.tzinfo is None:
            revoked_at = revoked_at.replace(tzinfo=UTC)
        return StoredRefreshToken(
            id=row.id, user_id=row.user_id, expires_at=expires_at, revoked_at=revoked_at
        )

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Revoke every live refresh token for a user.

        Used when the password changes (SCRUM-188): a password change that
        leaves previously issued sessions alive is half a fix — the whole point
        is to lock out whoever might already hold one.

        Idempotent by construction: rows already revoked are excluded by the
        WHERE, so their original revoked_at is preserved.
        """
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke(self, token_id: UUID) -> None:
        """Mark a token revoked. Idempotent — re-revoking keeps the first
        revoked_at so the original revocation time is preserved."""
        token = await self._session.get(RefreshToken, token_id)
        if token is None or token.revoked_at is not None:
            return
        token.revoked_at = datetime.now(UTC)
