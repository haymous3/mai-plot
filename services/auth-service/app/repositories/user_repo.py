"""DB access for users + user_pii.

Repository layer per CLAUDE.md §4 architecture rule — route handlers do
not touch SQLAlchemy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserPii


@dataclass(frozen=True)
class UserWithPhone:
    """View struct for repo callers — avoids leaking the ORM into services."""

    id: UUID
    role: str
    phone: str
    verified_status: str


@dataclass(frozen=True)
class UserCore:
    """Minimal user view for id-based lookups (refresh, auth dependency)."""

    id: UUID
    role: str
    verified_status: str


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_id(self, user_id: UUID) -> UserCore | None:
        """Fetch a live (not soft-deleted, active) user by id.

        Returns None for unknown, soft-deleted, or deactivated users so the
        refresh/auth paths reject tokens for accounts that no longer exist.
        """
        stmt = select(User.id, User.role, User.verified_status).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return UserCore(id=row.id, role=row.role, verified_status=row.verified_status)

    async def get_by_phone(self, phone: str) -> UserWithPhone | None:
        stmt = (
            select(User.id, User.role, UserPii.phone, User.verified_status)
            .join(UserPii, UserPii.user_id == User.id)
            .where(UserPii.phone == phone, User.deleted_at.is_(None))
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return UserWithPhone(
            id=row.id, role=row.role, phone=row.phone, verified_status=row.verified_status
        )

    async def create_with_pii(
        self,
        *,
        phone: str,
        role: str,
        email: str | None,
        seller_authority_type: str | None,
        full_name: str = "",
    ) -> UUID:
        """Insert a users row and its user_pii row in the same DB transaction.

        The caller owns the surrounding transaction boundary (the route
        handler's get_session dependency commits on success).
        """
        poa_status = "pending" if seller_authority_type == "power_of_attorney" else "not_applicable"
        user = User(
            role=role,
            email=email,
            seller_authority_type=seller_authority_type,
            poa_verified_status=poa_status,
        )
        self._session.add(user)
        await self._session.flush()
        pii = UserPii(user_id=user.id, phone=phone, full_name=full_name)
        self._session.add(pii)
        await self._session.flush()
        return user.id

    async def mark_phone_verified(self, user_id: UUID) -> None:
        user = await self._session.get(User, user_id)
        if user is None:
            return
        if user.verified_status == "unverified":
            user.verified_status = "phone_verified"
