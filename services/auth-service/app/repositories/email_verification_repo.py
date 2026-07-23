"""DB access for email_verification_tokens (SCRUM-152)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailVerificationToken


@dataclass(frozen=True)
class ActiveEmailToken:
    """View struct for the verify path — keeps the ORM out of the service."""

    id: UUID
    user_id: UUID
    email: str
    expires_at: datetime


class EmailVerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        email: str,
        token_hash: str,
        purpose: str,
        expires_at: datetime,
    ) -> UUID:
        token = EmailVerificationToken(
            user_id=user_id,
            email=email,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token.id

    async def get_active_by_hash(self, *, token_hash: str, purpose: str) -> ActiveEmailToken | None:
        """Return the unused token matching this (token_hash, purpose), or None.

        token_hash is UNIQUE so there is at most one row; the purpose guard
        stops a token minted for one flow from satisfying another.
        """
        stmt = select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.purpose == purpose,
            EmailVerificationToken.used_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ActiveEmailToken(
            id=row.id, user_id=row.user_id, email=row.email, expires_at=row.expires_at
        )

    async def mark_used(self, token_id: UUID) -> None:
        stmt = (
            update(EmailVerificationToken)
            .where(EmailVerificationToken.id == token_id)
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)

    async def invalidate_active(self, *, user_id: UUID, purpose: str) -> None:
        """Burn every still-unused token for this (user, purpose) — used on
        resend so a freshly-minted link supersedes any earlier ones (a user
        should never have two simultaneously-valid verification links)."""
        stmt = (
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.purpose == purpose,
                EmailVerificationToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
