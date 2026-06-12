"""DB writes for property_listings.

Repository layer per CLAUDE.md §4 — the service layer calls this, route
handlers never touch SQLAlchemy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.search_index import SearchDoc
from app.models import PropertyListing

# Columns a PATCH may set. Keys of the update dict are validated against this
# so the dynamic UPDATE can only touch intended columns.
_UPDATABLE_COLUMNS = frozenset(
    {
        "title",
        "description",
        "property_type",
        "address_text",
        "location",
        "lga",
        "state",
        "size_sqm",
        "asking_price_kobo",
        "sale_type",
        "urgency_tag",
        "expires_at",
    }
)

# Whitelisted ORDER BY fragments — keys come from a Literal in the schema, so
# the interpolated SQL is from a fixed set (values are always bound params).
_SORT_SQL = {
    "recency": "pl.created_at DESC",
    "price_asc": "pl.asking_price_kobo ASC",
    "price_desc": "pl.asking_price_kobo DESC",
    "urgency": "(pl.sale_type = 'distress') DESC, pl.expires_at ASC NULLS LAST, pl.created_at DESC",
}


@dataclass(frozen=True)
class NewListing:
    """The fields a create needs. location is a PostGIS WKT string
    (SRID=4326;POINT(lng lat)); the service builds it from lat/lng."""

    seller_id: UUID
    property_type: str
    title: str
    description: str | None
    address_text: str
    location_wkt: str
    lga: str
    state: str
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    expires_at: datetime


@dataclass(frozen=True)
class FeedFilters:
    state: str | None = None
    lga: str | None = None
    sale_type: str | None = None  # 'distress' | 'normal' | 'all'/None
    property_type: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    doc_status: str | None = None  # 'verified' | 'all'/None
    sort: str = "recency"
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class FeedRow:
    id: UUID
    title: str
    property_type: str
    state: str
    lga: str
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    expires_at: datetime | None
    status: str
    doc_verification_status: str
    view_count: int
    interest_count: int
    created_at: datetime
    seller_authority_type: str | None


@dataclass(frozen=True)
class DetailRow:
    id: UUID
    seller_id: UUID
    title: str
    description: str | None
    address_text: str
    lat: float
    lng: float
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    expires_at: datetime | None
    status: str
    view_count: int
    interest_count: int


@dataclass(frozen=True)
class MediaRow:
    media_type: str
    cdn_url: str
    sort_order: int


@dataclass(frozen=True)
class OwnerStatus:
    seller_id: UUID
    status: str
    sale_type: str


@dataclass(frozen=True)
class QueueRow:
    id: UUID
    seller_id: UUID
    title: str
    state: str
    lga: str
    asking_price_kobo: int
    sale_type: str
    status: str
    seller_authority_type: str | None
    created_at: datetime


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_feed(self, filters: FeedFilters) -> tuple[list[FeedRow], int]:
        """Active, non-deleted listings matching the filters, paginated.

        Joins users for seller_authority_type (shared DB). All user values are
        bound params; only the column/sort fragments — from a fixed whitelist —
        are interpolated, so there is no injection surface.
        """
        where = ["pl.deleted_at IS NULL", "pl.status = 'active'"]
        params: dict[str, object] = {}
        if filters.state:
            where.append("pl.state = :state")
            params["state"] = filters.state
        if filters.lga:
            where.append("pl.lga = :lga")
            params["lga"] = filters.lga
        if filters.sale_type and filters.sale_type != "all":
            where.append("pl.sale_type = :sale_type")
            params["sale_type"] = filters.sale_type
        if filters.property_type:
            where.append("pl.property_type = :ptype")
            params["ptype"] = filters.property_type
        if filters.price_min is not None:
            where.append("pl.asking_price_kobo >= :pmin")
            params["pmin"] = filters.price_min
        if filters.price_max is not None:
            where.append("pl.asking_price_kobo <= :pmax")
            params["pmax"] = filters.price_max
        if filters.doc_status == "verified":
            where.append("pl.doc_verification_status = 'verified'")
        where_sql = " AND ".join(where)
        order_sql = _SORT_SQL.get(filters.sort, _SORT_SQL["recency"])

        total = (
            await self._session.execute(
                text(f"SELECT COUNT(*) FROM property_listings pl WHERE {where_sql}"), params
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                text(
                    f"""
                    SELECT pl.id, pl.title, pl.property_type, pl.state, pl.lga, pl.size_sqm,
                           pl.asking_price_kobo, pl.sale_type, pl.urgency_tag, pl.expires_at,
                           pl.status, pl.doc_verification_status, pl.view_count,
                           pl.interest_count, pl.created_at, u.seller_authority_type
                    FROM property_listings pl
                    LEFT JOIN users u ON u.id = pl.seller_id
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {
                    **params,
                    "limit": filters.page_size,
                    "offset": (filters.page - 1) * filters.page_size,
                },
            )
        ).all()

        items = [
            FeedRow(
                id=r.id,
                title=r.title,
                property_type=r.property_type,
                state=r.state,
                lga=r.lga,
                size_sqm=r.size_sqm,
                asking_price_kobo=r.asking_price_kobo,
                sale_type=r.sale_type,
                urgency_tag=r.urgency_tag,
                expires_at=r.expires_at,
                status=r.status,
                doc_verification_status=r.doc_verification_status,
                view_count=r.view_count,
                interest_count=r.interest_count,
                created_at=r.created_at,
                seller_authority_type=r.seller_authority_type,
            )
            for r in rows
        ]
        return items, int(total)

    async def get_detail(self, listing_id: UUID) -> DetailRow | None:
        """A single non-deleted listing with lat/lng extracted from PostGIS."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT pl.id, pl.seller_id, pl.title, pl.description, pl.address_text,
                           ST_Y(pl.location::geometry) AS lat, ST_X(pl.location::geometry) AS lng,
                           pl.size_sqm, pl.asking_price_kobo, pl.sale_type, pl.urgency_tag,
                           pl.expires_at, pl.status, pl.view_count, pl.interest_count
                    FROM property_listings pl
                    WHERE pl.id = :id AND pl.deleted_at IS NULL
                    """
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return DetailRow(
            id=row.id,
            seller_id=row.seller_id,
            title=row.title,
            description=row.description,
            address_text=row.address_text,
            lat=row.lat,
            lng=row.lng,
            size_sqm=row.size_sqm,
            asking_price_kobo=row.asking_price_kobo,
            sale_type=row.sale_type,
            urgency_tag=row.urgency_tag,
            expires_at=row.expires_at,
            status=row.status,
            view_count=row.view_count,
            interest_count=row.interest_count,
        )

    async def list_media(self, listing_id: UUID) -> list[MediaRow]:
        rows = (
            await self._session.execute(
                text(
                    "SELECT media_type, cdn_url, sort_order FROM listing_media "
                    "WHERE listing_id = :id ORDER BY sort_order"
                ),
                {"id": listing_id},
            )
        ).all()
        return [
            MediaRow(media_type=r.media_type, cdn_url=r.cdn_url, sort_order=r.sort_order)
            for r in rows
        ]

    async def count_media(self, listing_id: UUID, media_type: str) -> int:
        """How many photos/videos a listing already has (for the per-type cap)."""
        total = (
            await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM listing_media WHERE listing_id = :id AND media_type = :t"
                ),
                {"id": listing_id, "t": media_type},
            )
        ).scalar_one()
        return int(total)

    async def insert_media(
        self,
        *,
        listing_id: UUID,
        media_type: str,
        s3_key: str,
        cdn_url: str,
        sort_order: int,
        size_bytes: int,
    ) -> UUID:
        """Insert a listing_media row and return its id."""
        media_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO listing_media
                        (listing_id, media_type, s3_key, cdn_url, sort_order, size_bytes)
                    VALUES (:lid, :mtype, :s3, :cdn, :sort, :size)
                    RETURNING id
                    """
                ),
                {
                    "lid": listing_id,
                    "mtype": media_type,
                    "s3": s3_key,
                    "cdn": cdn_url,
                    "sort": sort_order,
                    "size": size_bytes,
                },
            )
        ).scalar_one()
        assert isinstance(media_id, UUID)
        return media_id

    async def list_review_queue(
        self,
        *,
        status: str,
        authority_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[QueueRow], int]:
        """Listings in a given status for the admin review queue. PoA sellers
        are prioritised (shown first); within that, oldest-first (FIFO)."""
        where = ["pl.deleted_at IS NULL", "pl.status = :status"]
        params: dict[str, object] = {"status": status}
        if authority_type:
            where.append("u.seller_authority_type = :authority_type")
            params["authority_type"] = authority_type
        where_sql = " AND ".join(where)

        total = (
            await self._session.execute(
                text(
                    f"SELECT COUNT(*) FROM property_listings pl "
                    f"LEFT JOIN users u ON u.id = pl.seller_id WHERE {where_sql}"
                ),
                params,
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                text(
                    f"""
                    SELECT pl.id, pl.seller_id, pl.title, pl.state, pl.lga,
                           pl.asking_price_kobo, pl.sale_type, pl.status, pl.created_at,
                           u.seller_authority_type
                    FROM property_listings pl
                    LEFT JOIN users u ON u.id = pl.seller_id
                    WHERE {where_sql}
                    ORDER BY (u.seller_authority_type = 'power_of_attorney') DESC,
                             pl.created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        ).all()
        items = [
            QueueRow(
                id=r.id,
                seller_id=r.seller_id,
                title=r.title,
                state=r.state,
                lga=r.lga,
                asking_price_kobo=r.asking_price_kobo,
                sale_type=r.sale_type,
                status=r.status,
                seller_authority_type=r.seller_authority_type,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, int(total)

    async def set_review_status(
        self, listing_id: UUID, *, new_status: str, rejection_reason: str | None
    ) -> None:
        """Apply an admin review decision: set status (+ rejection_reason)."""
        await self._session.execute(
            text(
                "UPDATE property_listings "
                "SET status = :s, rejection_reason = :r, updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"s": new_status, "r": rejection_reason, "id": listing_id},
        )

    async def get_search_doc(self, listing_id: UUID) -> SearchDoc | None:
        """Build the search-index document for a listing (any status — search
        filters to active itself). Joins users for seller_authority_type."""
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT pl.id, pl.title, pl.description, pl.property_type, pl.state, pl.lga,
                           pl.address_text,
                           ST_Y(pl.location::geometry) AS lat, ST_X(pl.location::geometry) AS lng,
                           pl.size_sqm, pl.asking_price_kobo, pl.sale_type, pl.urgency_tag,
                           pl.expires_at, pl.status, pl.doc_verification_status,
                           pl.view_count, pl.interest_count, pl.created_at,
                           u.seller_authority_type
                    FROM property_listings pl
                    LEFT JOIN users u ON u.id = pl.seller_id
                    WHERE pl.id = :id AND pl.deleted_at IS NULL
                    """
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return SearchDoc(
            id=row.id,
            title=row.title,
            description=row.description,
            property_type=row.property_type,
            state=row.state,
            lga=row.lga,
            address_text=row.address_text,
            lat=row.lat,
            lng=row.lng,
            size_sqm=row.size_sqm,
            asking_price_kobo=row.asking_price_kobo,
            sale_type=row.sale_type,
            urgency_tag=row.urgency_tag,
            expires_at=row.expires_at,
            status=row.status,
            doc_verification_status=row.doc_verification_status,
            seller_authority_type=row.seller_authority_type,
            view_count=row.view_count,
            interest_count=row.interest_count,
            created_at=row.created_at,
        )

    async def get_owner_status(self, listing_id: UUID) -> OwnerStatus | None:
        """Owner + status + sale_type for a live listing (PATCH auth + rules)."""
        row = (
            await self._session.execute(
                text(
                    "SELECT seller_id, status, sale_type FROM property_listings "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": listing_id},
            )
        ).first()
        if row is None:
            return None
        return OwnerStatus(seller_id=row.seller_id, status=row.status, sale_type=row.sale_type)

    async def apply_update(self, listing_id: UUID, updates: dict[str, object]) -> None:
        """Partial UPDATE of a listing. Only whitelisted columns are set;
        updated_at is always refreshed. `location` is a PostGIS WKT string —
        the Geography column's bind processor casts it, same as on create."""
        safe = {k: v for k, v in updates.items() if k in _UPDATABLE_COLUMNS}
        if not safe:
            return
        stmt = (
            sa_update(PropertyListing)
            .where(PropertyListing.id == listing_id)
            .values({**safe, "updated_at": datetime.now(UTC)})
        )
        await self._session.execute(stmt)

    async def create(self, listing: NewListing) -> UUID:
        """Insert a listing with status 'pending_review' (the DB default) and
        return its id. The caller's get_session dependency commits."""
        row = PropertyListing(
            seller_id=listing.seller_id,
            property_type=listing.property_type,
            title=listing.title,
            description=listing.description,
            address_text=listing.address_text,
            location=listing.location_wkt,
            lga=listing.lga,
            state=listing.state,
            size_sqm=listing.size_sqm,
            asking_price_kobo=listing.asking_price_kobo,
            sale_type=listing.sale_type,
            urgency_tag=listing.urgency_tag,
            status="pending_review",
            expires_at=listing.expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row.id
