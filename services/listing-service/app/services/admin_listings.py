"""The admin listing console — browse + detail (SCRUM-215).

Before this, the entire admin listing surface was `GET /admin/listings/queue`
pinned to `status=pending_review` and the approve/reject decision on it. Two
consequences, both live on staging:

  * **An approved listing left the admin's world.** 13 of the 14 listings were
    unreachable from the admin side — active, under offer, paused, sold. There
    was no "show me this property" for anything already published.
  * **An admin approved a listing without seeing it.** The queue row carries the
    title, state/LGA, price, sale type and the seller's authority. No photo, no
    description, no address, no documents. The detail here is the fix for that,
    not a nicety.

Read-only. Status changes live in `admin_listing_actions` (SCRUM-215 PR2).
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.seller_repo import SellerRepository
from app.schemas.listing import (
    AdminAuditEntry,
    AdminListingDetailResponse,
    AdminListingItem,
    AdminListingsResponse,
    GeoPoint,
    MediaItem,
    Pagination,
    SellerBlock,
)


class ListingNotFound(Exception):
    """No live listing with that id."""


class AdminListingsService:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        sellers: SellerRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._listings = listings
        self._sellers = sellers
        self._audit = audit

    async def browse(
        self,
        *,
        search: str | None,
        status: str | None,
        authority_type: str | None,
        state: str | None,
        page: int,
        page_size: int,
    ) -> AdminListingsResponse:
        rows, total = await self._listings.list_for_admin(
            search=search,
            status=status,
            authority_type=authority_type,
            state=state,
            page=page,
            page_size=page_size,
        )
        items = [
            AdminListingItem(
                id=r.id,
                seller_id=r.seller_id,
                title=r.title,
                property_type=r.property_type,
                state=r.state,
                lga=r.lga,
                asking_price_kobo=r.asking_price_kobo,
                sale_type=r.sale_type,
                urgency_tag=r.urgency_tag,
                status=r.status,
                doc_verification_status=r.doc_verification_status,
                view_count=r.view_count,
                interest_count=r.interest_count,
                expires_at=r.expires_at,
                created_at=r.created_at,
                seller_authority_type=r.seller_authority_type,
                cover_photo_url=r.cover_photo_url,
            )
            for r in rows
        ]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return AdminListingsResponse(
            data=items,
            pagination=Pagination(
                page=page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )

    async def detail(self, listing_id: UUID) -> AdminListingDetailResponse:
        row = await self._listings.get_admin_detail(listing_id)
        if row is None:
            raise ListingNotFound()

        media = await self._listings.list_media(listing_id)
        history = await self._audit.list_for_entity(entity_type="listing", entity_id=listing_id)
        # A seller who has been soft-deleted leaves the listing readable but the
        # block empty — an orphaned listing is exactly the kind of thing an admin
        # opens this page to find, so it must not 404 on the way.
        seller = await self._sellers.get_seller_public(row.seller_id)

        return AdminListingDetailResponse(
            id=row.id,
            seller=SellerBlock(
                id=row.seller_id,
                authority_type=seller.authority_type if seller else None,
                poa_owner_name=seller.poa_owner_name if seller else None,
            ),
            title=row.title,
            property_type=row.property_type,
            description=row.description,
            address_text=row.address_text,
            location=GeoPoint(lat=row.lat, lng=row.lng),
            state=row.state,
            lga=row.lga,
            size_sqm=float(row.size_sqm) if row.size_sqm is not None else None,
            asking_price_kobo=row.asking_price_kobo,
            sale_type=row.sale_type,
            urgency_tag=row.urgency_tag,
            status=row.status,
            doc_verification_status=row.doc_verification_status,
            rejection_reason=row.rejection_reason,
            view_count=row.view_count,
            interest_count=row.interest_count,
            expires_at=row.expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            media=[
                MediaItem(type=m.media_type, url=m.cdn_url, sort_order=m.sort_order) for m in media
            ],
            history=[
                AdminAuditEntry(
                    id=h.id,
                    actor_id=h.actor_id,
                    actor_role=h.actor_role,
                    action=h.action,
                    old_value=h.old_value,
                    new_value=h.new_value,
                    created_at=h.created_at,
                )
                for h in history
            ],
        )
