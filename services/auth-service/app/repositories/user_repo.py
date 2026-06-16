"""DB access for users + user_pii.

Repository layer per CLAUDE.md §4 architecture rule — route handlers do
not touch SQLAlchemy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
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


@dataclass(frozen=True)
class UserAuthority:
    """Role + seller authority, for the NIN eligibility gate."""

    role: str
    seller_authority_type: str | None


@dataclass(frozen=True)
class PoaQueueRow:
    """One pending PoA submission for the legal-team review queue."""

    user_id: UUID
    owner_name: str | None
    submitted_at: datetime


@dataclass(frozen=True)
class PoaReviewTarget:
    """What the review service needs: current status, the seller's phone (for
    the decision SMS), and whether a document is actually on file."""

    poa_verified_status: str
    phone: str
    has_document: bool


@dataclass(frozen=True)
class PoaState:
    """Role + authority + current PoA verification status, plus whether a
    document is already on file. Drives the PoA upload eligibility/conflict
    checks. (Registration pre-sets poa_verified_status='pending' for PoA
    sellers before any upload, so the conflict check keys off has_document,
    not the status, to allow the first upload through.)"""

    role: str
    seller_authority_type: str | None
    poa_verified_status: str
    has_document: bool


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

    async def get_active_by_email(self, email: str) -> UserCore | None:
        """Fetch a live user by email for password login. Returns None for
        unknown, soft-deleted, or deactivated accounts."""
        stmt = select(User.id, User.role, User.verified_status).where(
            User.email == email,
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

    async def has_bvn(self, user_id: UUID) -> bool:
        """True if this user already has a BVN on file."""
        stmt = select(UserPii.bvn_hash).where(UserPii.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def find_user_by_bvn_lookup(self, bvn_lookup: str) -> UUID | None:
        """Return the user_id that already owns this BVN (via the
        deterministic lookup hash), or None. Used for cross-account dedup."""
        stmt = select(UserPii.user_id).where(UserPii.bvn_lookup == bvn_lookup)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_bvn_verified(self, user_id: UUID, *, bvn_hash: str, bvn_lookup: str) -> None:
        """Persist the BVN hashes and advance verified_status.

        Writes only the bcrypt hash and the HMAC lookup — never the BVN.
        verified_status moves to id_verified (unless already fully_verified).
        """
        pii = await self._session.get(UserPii, user_id)
        if pii is not None:
            pii.bvn_hash = bvn_hash
            pii.bvn_lookup = bvn_lookup
            pii.updated_at = datetime.now(UTC)
        user = await self._session.get(User, user_id)
        if user is not None and user.verified_status != "fully_verified":
            user.verified_status = "id_verified"

    async def get_authority(self, user_id: UUID) -> UserAuthority | None:
        """Role + seller_authority_type for a live user (NIN eligibility)."""
        stmt = select(User.role, User.seller_authority_type).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return UserAuthority(role=row.role, seller_authority_type=row.seller_authority_type)

    async def has_nin(self, user_id: UUID) -> bool:
        """True if this user already has a NIN on file."""
        stmt = select(UserPii.nin_hash).where(UserPii.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def get_poa_state(self, user_id: UUID) -> PoaState | None:
        """Role + authority + PoA status + whether a document is on file, for
        a live user (PoA upload gate). Joins user_pii for the document key."""
        stmt = (
            select(
                User.role,
                User.seller_authority_type,
                User.poa_verified_status,
                UserPii.poa_document_s3_key,
            )
            .join(UserPii, UserPii.user_id == User.id)
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return PoaState(
            role=row.role,
            seller_authority_type=row.seller_authority_type,
            poa_verified_status=row.poa_verified_status,
            has_document=row.poa_document_s3_key is not None,
        )

    async def set_poa_document(self, user_id: UUID, *, s3_key: str) -> None:
        """Record the uploaded PoA document key and move poa_verified_status
        to 'pending' (awaiting legal-team review). Only the private S3 key is
        stored — never the document bytes."""
        pii = await self._session.get(UserPii, user_id)
        if pii is not None:
            pii.poa_document_s3_key = s3_key
            pii.updated_at = datetime.now(UTC)
        user = await self._session.get(User, user_id)
        if user is not None:
            user.poa_verified_status = "pending"

    async def list_poa_queue(self, *, page: int, page_size: int) -> tuple[list[PoaQueueRow], int]:
        """Pending PoA submissions awaiting legal-team review (status='pending'
        with a document on file), oldest-first. Returns (rows, total)."""
        base = (
            select(User.id, UserPii.poa_document_owner_name, UserPii.updated_at)
            .join(UserPii, UserPii.user_id == User.id)
            .where(
                User.poa_verified_status == "pending",
                UserPii.poa_document_s3_key.is_not(None),
                User.deleted_at.is_(None),
            )
        )
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self._session.execute(
                base.order_by(UserPii.updated_at.asc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
        items = [
            PoaQueueRow(
                user_id=row.id,
                owner_name=row.poa_document_owner_name,
                submitted_at=row.updated_at,
            )
            for row in rows
        ]
        return items, int(total)

    async def get_poa_review_target(self, user_id: UUID) -> PoaReviewTarget | None:
        """Current PoA status + seller phone + whether a document exists, for a
        live user. None if the user does not exist / is not live."""
        stmt = (
            select(
                User.poa_verified_status,
                UserPii.phone,
                UserPii.poa_document_s3_key,
            )
            .join(UserPii, UserPii.user_id == User.id)
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return PoaReviewTarget(
            poa_verified_status=row.poa_verified_status,
            phone=row.phone,
            has_document=row.poa_document_s3_key is not None,
        )

    async def set_poa_verification(self, user_id: UUID, *, status: str) -> None:
        """Apply a legal-team decision: move poa_verified_status to
        'verified' or 'rejected'."""
        user = await self._session.get(User, user_id)
        if user is not None:
            user.poa_verified_status = status
            user.updated_at = datetime.now(UTC)

    async def find_user_by_nin_lookup(self, nin_lookup: str) -> UUID | None:
        """Return the user_id that already owns this NIN, or None."""
        stmt = select(UserPii.user_id).where(UserPii.nin_lookup == nin_lookup)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_nin_verified(self, user_id: UUID, *, nin_hash: str, nin_lookup: str) -> None:
        """Persist the NIN hashes and advance verified_status to id_verified
        (unless already fully_verified). Writes only hashes — never the NIN."""
        pii = await self._session.get(UserPii, user_id)
        if pii is not None:
            pii.nin_hash = nin_hash
            pii.nin_lookup = nin_lookup
            pii.updated_at = datetime.now(UTC)
        user = await self._session.get(User, user_id)
        if user is not None and user.verified_status != "fully_verified":
            user.verified_status = "id_verified"
