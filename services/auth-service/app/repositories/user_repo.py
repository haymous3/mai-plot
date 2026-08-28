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
class UserAccount:
    """Everything GET /auth/me needs about the caller, in one read.

    ⚠️ BVN and NIN are exposed as BOOLEANS, never values. Both are stored only
    as bcrypt hashes (CLAUDE.md §4) and the hash must never leave the service —
    it is offline-crackable against an 11-digit space.
    """

    id: UUID
    role: str
    verified_status: str
    email: str | None
    phone: str
    full_name: str
    seller_authority_type: str | None
    poa_verified_status: str
    bvn_verified: bool
    nin_verified: bool
    # The private-bucket KEY, not a URL. The route mints a short-lived
    # pre-signed URL from it; the key itself never reaches the client.
    avatar_s3_key: str | None
    location: str | None


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
class SellerPoaStatus:
    """A seller's own PoA tracking view (SCRUM-137): authority + verification
    status + whether a document is on file + when it was last submitted."""

    seller_authority_type: str | None
    poa_verified_status: str
    has_document: bool
    submitted_at: datetime | None


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

    async def get_account(self, user_id: UUID) -> UserAccount | None:
        """The caller's own account for GET /auth/me. None if unknown, soft
        deleted or deactivated, so a token for a dead account reads as absent
        rather than half-populated."""
        stmt = (
            select(
                User.id,
                User.role,
                User.verified_status,
                User.email,
                User.seller_authority_type,
                User.poa_verified_status,
                UserPii.phone,
                UserPii.full_name,
                # Presence only. The hashes themselves never leave the service.
                UserPii.bvn_hash.is_not(None).label("bvn_verified"),
                UserPii.nin_hash.is_not(None).label("nin_verified"),
                UserPii.avatar_s3_key,
                UserPii.location,
            )
            .join(UserPii, UserPii.user_id == User.id)
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                UserPii.deleted_at.is_(None),
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return UserAccount(
            id=row.id,
            role=row.role,
            verified_status=row.verified_status,
            email=row.email,
            phone=row.phone,
            full_name=row.full_name,
            seller_authority_type=row.seller_authority_type,
            poa_verified_status=row.poa_verified_status,
            bvn_verified=row.bvn_verified,
            nin_verified=row.nin_verified,
            avatar_s3_key=row.avatar_s3_key,
            location=row.location,
        )

    async def set_avatar_key(self, user_id: UUID, *, key: str | None) -> tuple[bool, str | None]:
        """Point the user at a new avatar object.

        Returns (row_found, previous_key). Both halves matter and neither can
        be inferred from the other: a missing row and a row with no photo yet
        would both report `None` as the previous key, and the caller needs to
        tell "no such user" from "no photo before now".

        The PREVIOUS key is what lets the caller delete the superseded object.
        Every upload mints a fresh uuid key, so without this the bucket would
        accumulate one orphan per re-upload with nothing pointing at it.
        """
        pii = await self._session.get(UserPii, user_id)
        if pii is None:
            return False, None
        previous = pii.avatar_s3_key
        pii.avatar_s3_key = key
        return True, previous

    async def soft_delete(self, user_id: UUID) -> tuple[bool, str | None]:
        """Mark the account deleted. Returns (deleted, avatar_key_to_purge).

        `deleted` is False when there was no live row to delete — already
        gone, or never existed. It cannot be inferred from the key, since a
        successful delete of an account with no photo also yields None.

        Sets `deleted_at` on BOTH tables. The trigger from migration 0009
        mirrors users.deleted_at onto user_pii already, but writing it here
        keeps the ORM's in-session view consistent with the database within
        the same transaction — an ORM write does not see a trigger's effect
        until it refreshes.

        Soft, not hard: transactions, escrow movements and audit rows must
        survive for CBN/AMLON. Freeing the phone and email for reuse is
        handled by the partial unique indexes in migrations 0009 and 0010, so
        this needs no extra work to release those identifiers.
        """
        now = datetime.now(UTC)
        user = await self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            return False, None
        user.deleted_at = now
        user.is_active = False

        avatar_key: str | None = None
        pii = await self._session.get(UserPii, user_id)
        if pii is not None:
            pii.deleted_at = now
            # Drop the pointer as part of the same write. The object itself is
            # deleted by the service; a face photo has no CBN retention basis
            # the way the financial ledger does, so NDPR erasure wins here.
            avatar_key = pii.avatar_s3_key
            pii.avatar_s3_key = None
        return True, avatar_key

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
        """The account that owns this phone FOR PHONE VERIFICATION.

        Filtered to verification_channel = 'phone' (SCRUM-183). That predicate
        matches the partial unique index in migration 0008, so at most one row
        can ever match — which is what makes it safe for otp_verification to
        issue tokens off this lookup. Without the filter a phone shared with an
        email-verified account would be ambiguous and could verify the wrong
        person.
        """
        stmt = (
            select(User.id, User.role, UserPii.phone, User.verified_status)
            .join(UserPii, UserPii.user_id == User.id)
            .where(
                UserPii.phone == phone,
                UserPii.verification_channel == "phone",
                # Both deleted_at checks, matching the partial unique index in
                # migration 0009 exactly. users.deleted_at is the source of
                # truth; user_pii.deleted_at mirrors it via trigger and is what
                # the index can actually see. Filtering on both keeps this
                # query and the index describing the same set even if the two
                # ever drift.
                UserPii.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
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
        verification_channel: str = "email",
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
        pii = UserPii(
            user_id=user.id,
            phone=phone,
            full_name=full_name,
            verification_channel=verification_channel,
        )
        self._session.add(pii)
        await self._session.flush()
        return user.id

    async def email_taken_by_other(self, email: str, *, user_id: UUID) -> bool:
        """True if a live user OTHER than user_id already owns this email.
        Pre-check for the profile update — mirrors the phone/BVN uniqueness
        pre-checks; the unique constraint on users.email is the backstop."""
        stmt = select(User.id).where(
            User.email == email,
            User.id != user_id,
            User.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).first() is not None

    async def update_profile(
        self,
        user_id: UUID,
        *,
        full_name: str,
        email: str | None,
        location: str | None = None,
        set_location: bool = False,
    ) -> None:
        """Set the caller's display name (user_pii) and, when supplied, email
        (users). Only touches the caller's own rows; email is left unchanged
        when None so a re-submit without email does not clear an existing one.

        `location` follows a different rule from `email` on purpose: it is
        writable to NULL. `set_location` says "the caller sent this field", so
        clearing a location is expressible, while a caller that omits it
        entirely leaves the stored value alone. Reusing the email convention
        would have made a location impossible to remove once set."""
        pii = await self._session.get(UserPii, user_id)
        if pii is not None:
            pii.full_name = full_name
            if set_location:
                pii.location = location
        if email is not None:
            user = await self._session.get(User, user_id)
            if user is not None:
                user.email = email

    async def set_seller_authority(self, user_id: UUID, *, authority_type: str) -> None:
        """Declare a seller's selling authority after registration (SCRUM-132).

        A power_of_attorney seller enters the PoA review queue (poa_verified_status
        'pending', which gates PoA-document upload); an owner is 'not_applicable'.
        Mirrors the create_with_pii logic so a deferred declaration behaves exactly
        like declaring it at registration."""
        user = await self._session.get(User, user_id)
        if user is None:
            return
        user.seller_authority_type = authority_type
        user.poa_verified_status = (
            "pending" if authority_type == "power_of_attorney" else "not_applicable"
        )

    async def mark_phone_verified(self, user_id: UUID) -> None:
        user = await self._session.get(User, user_id)
        if user is None:
            return
        if user.verified_status == "unverified":
            user.verified_status = "phone_verified"

    async def mark_email_verified(self, user_id: UUID) -> None:
        """Advance an unverified user to 'email_verified' after a magic-link
        confirm (SCRUM-152). Only lifts 'unverified' — a user who is already
        further along (phone/id/fully) keeps their higher status."""
        user = await self._session.get(User, user_id)
        if user is None:
            return
        if user.verified_status == "unverified":
            user.verified_status = "email_verified"

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

    async def get_seller_poa_status(self, user_id: UUID) -> SellerPoaStatus | None:
        """A live seller's own PoA status view (SCRUM-137). submitted_at is the
        PoA row's last-touch time when a document is on file (mirrors the queue's
        submitted_at). None if the user is not live."""
        stmt = (
            select(
                User.seller_authority_type,
                User.poa_verified_status,
                UserPii.poa_document_s3_key,
                UserPii.updated_at,
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
        has_document = row.poa_document_s3_key is not None
        return SellerPoaStatus(
            seller_authority_type=row.seller_authority_type,
            poa_verified_status=row.poa_verified_status,
            has_document=has_document,
            submitted_at=row.updated_at if has_document else None,
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

    async def get_poa_document_key(self, user_id: UUID) -> str | None:
        """The private-bucket key of a live user's PoA document, or None if the
        user/doc is absent. Used to serve the document to the legal team."""
        stmt = (
            select(UserPii.poa_document_s3_key)
            .join(User, User.id == UserPii.user_id)
            .where(
                UserPii.user_id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

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
