"""Cross-service read of seller eligibility from the shared auth tables.

The seller's authority + verification state lives in auth-service's `users`
and `user_pii` tables. listing-service reads them directly: the database is
shared and property_listings.seller_id already has a real FK to users(id),
so the boundary is already crossed at the schema level. This is a deliberate
trade against CLAUDE.md §3 ("REST internally") that holds while services
share one DB — when they split onto separate databases this becomes a REST
call to auth-service. The query is read-only and uses text() to make the
cross-service ownership explicit (no ORM model for another service's table).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SellerEligibility:
    role: str
    seller_authority_type: str | None
    poa_verified_status: str
    verified_status: str
    has_identity_document: bool


@dataclass(frozen=True)
class SellerPublic:
    """The non-sensitive seller fields shown on a listing detail page."""

    authority_type: str | None
    poa_owner_name: str | None


class SellerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_eligibility(self, seller_id: UUID) -> SellerEligibility | None:
        """Role + authority + verification state for a live seller, or None
        if the user is unknown, soft-deleted, or deactivated."""
        stmt = text(
            """
            SELECT u.role,
                   u.seller_authority_type,
                   u.poa_verified_status,
                   u.verified_status,
                   (p.bvn_hash IS NOT NULL OR p.nin_hash IS NOT NULL) AS has_identity_document
            FROM users u
            LEFT JOIN user_pii p ON p.user_id = u.id
            WHERE u.id = :sid
              AND u.deleted_at IS NULL
              AND u.is_active IS TRUE
            """
        )
        row = (await self._session.execute(stmt, {"sid": seller_id})).first()
        if row is None:
            return None
        return SellerEligibility(
            role=row.role,
            seller_authority_type=row.seller_authority_type,
            poa_verified_status=row.poa_verified_status,
            verified_status=row.verified_status,
            has_identity_document=bool(row.has_identity_document),
        )

    async def get_seller_public(self, seller_id: UUID) -> SellerPublic | None:
        """Public seller fields for a listing detail page (no contact PII)."""
        stmt = text(
            """
            SELECT u.seller_authority_type, p.poa_document_owner_name AS poa_owner_name
            FROM users u
            LEFT JOIN user_pii p ON p.user_id = u.id
            WHERE u.id = :sid AND u.deleted_at IS NULL
            """
        )
        row = (await self._session.execute(stmt, {"sid": seller_id})).first()
        if row is None:
            return None
        return SellerPublic(
            authority_type=row.seller_authority_type,
            poa_owner_name=row.poa_owner_name,
        )
