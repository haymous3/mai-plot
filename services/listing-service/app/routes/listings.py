"""/listings route handlers.

Handlers are thin: build the Pydantic request, call the service, translate
domain errors to HTTP responses matching api-contracts.md. No DB calls here.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.adapters.search_index import SearchParams
from app.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_express_interest_service,
    get_listing_create_service,
    get_listing_detail_service,
    get_listing_query_service,
    get_listing_search_service,
    get_listing_update_service,
    get_media_upload_service,
    get_saved_listing_service,
    get_seller_listings_service,
)
from app.repositories.listing_repo import FeedFilters
from app.schemas.listing import (
    CreateListingRequest,
    CreateListingResponse,
    ExpressInterestRequest,
    ExpressInterestResponse,
    FeedResponse,
    ListingDetailResponse,
    ListingStatusResponse,
    MediaType,
    MediaUploadResponse,
    SavedResponse,
    SearchResponse,
    SellerListingsResponse,
    SortOption,
    UpdateListingRequest,
    UpdateListingResponse,
)
from app.security import CurrentUser
from app.services.express_interest import ExpressInterestService
from app.services.listing_create import (
    BvnRequired,
    CreateListingInput,
    ListingCreateService,
    NotSeller,
)
from app.services.listing_detail import ListingDetailService
from app.services.listing_query import ListingQueryService
from app.services.listing_rules import InvalidUrgency
from app.services.listing_search import ListingSearchService
from app.services.listing_update import (
    CannotEditSoldListing,
    ListingNotFound,
    ListingUpdateService,
    NotListingOwner,
)
from app.services.media import InvalidMedia
from app.services.media_upload import (
    MediaLimitExceeded,
    MediaStorageUnavailable,
    MediaUploadService,
)
from app.services.poa_guard import PoaNotVerified
from app.services.saved_listings import SavedListingService
from app.services.seller_listings import (
    ListingNotFound as SellerListingNotFound,
)
from app.services.seller_listings import (
    ListingNotPausable,
    SellerListingsService,
)
from app.services.seller_listings import (
    NotListingOwner as SellerNotListingOwner,
)

router = APIRouter(prefix="/listings", tags=["listings"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("", response_model=FeedResponse)
async def get_feed(
    service: Annotated[ListingQueryService, Depends(get_listing_query_service)],
    state: str | None = None,
    lga: str | None = None,
    sale_type: str | None = Query(default=None, pattern="^(distress|normal|all)$"),
    property_type: str | None = Query(default=None, pattern="^(land|residential|commercial)$"),
    price_min: int | None = Query(default=None, ge=0),
    price_max: int | None = Query(default=None, ge=0),
    doc_status: str | None = Query(default=None, pattern="^(verified|all)$"),
    sort: SortOption = "recency",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> FeedResponse:
    filters = FeedFilters(
        state=state,
        lga=lga,
        sale_type=sale_type,
        property_type=property_type,
        price_min=price_min,
        price_max=price_max,
        doc_status=doc_status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return await service.get_feed(filters)


@router.get("/search", response_model=SearchResponse)
async def search_listings(
    service: Annotated[ListingSearchService, Depends(get_listing_search_service)],
    q: str | None = None,
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0),
    state: str | None = None,
    lga: str | None = None,
    sale_type: str | None = Query(default=None, pattern="^(distress|normal|all)$"),
    property_type: str | None = Query(default=None, pattern="^(land|residential|commercial)$"),
    price_min: int | None = Query(default=None, ge=0),
    price_max: int | None = Query(default=None, ge=0),
    doc_status: str | None = Query(default=None, pattern="^(verified|all)$"),
    sort: SortOption = "recency",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SearchResponse | JSONResponse:
    # Geo is all-or-nothing: lat, lng and radius_km must be supplied together.
    geo = (lat, lng, radius_km)
    if any(v is not None for v in geo) and any(v is None for v in geo):
        return _error(
            422,
            "GEO_PARAMS_INCOMPLETE",
            "lat, lng and radius_km must all be provided together for a geo search.",
        )
    params = SearchParams(
        q=q,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        state=state,
        lga=lga,
        sale_type=sale_type,
        property_type=property_type,
        price_min=price_min,
        price_max=price_max,
        doc_status=doc_status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return await service.search(params)


@router.get("/saved", response_model=FeedResponse)
async def list_saved_listings(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SavedListingService, Depends(get_saved_listing_service)],
) -> FeedResponse:
    """The caller's saved listings as feed cards (SCRUM-95). Declared before
    /{listing_id} so the literal path wins the match."""
    return await service.list_saved(current_user.user_id)


@router.get("/mine", response_model=SellerListingsResponse)
async def list_my_listings(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerListingsService, Depends(get_seller_listings_service)],
) -> SellerListingsResponse:
    """The caller's own listings for "My Listings" (SCRUM-98). Declared before
    /{listing_id} so the literal path wins."""
    return await service.list_mine(current_user.user_id)


@router.get("/{listing_id}", response_model=ListingDetailResponse)
async def get_listing_detail(
    listing_id: UUID,
    viewer: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
    service: Annotated[ListingDetailService, Depends(get_listing_detail_service)],
) -> ListingDetailResponse | JSONResponse:
    detail = await service.get_detail(listing_id=listing_id, viewer=viewer)
    if detail is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
        )
    return detail


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateListingResponse)
async def create_listing(
    body: CreateListingRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ListingCreateService, Depends(get_listing_create_service)],
) -> CreateListingResponse | JSONResponse:
    try:
        result = await service.create(
            seller_id=current_user.user_id,
            data=CreateListingInput(
                title=body.title,
                property_type=body.property_type,
                description=body.description,
                address_text=body.address_text,
                lat=body.location.lat,
                lng=body.location.lng,
                lga=body.lga,
                state=body.state,
                size_sqm=body.size_sqm,
                asking_price_kobo=body.asking_price_kobo,
                sale_type=body.sale_type,
                urgency_tag=body.urgency_tag,
            ),
        )
    except NotSeller:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "SELLER_ROLE_REQUIRED",
            "Only sellers can create listings.",
        )
    except BvnRequired:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "BVN_REQUIRED",
            "Complete identity (BVN/NIN) verification before listing a property.",
        )
    except PoaNotVerified:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "POA_NOT_VERIFIED",
            "Your power-of-attorney document must be verified before you can publish a listing.",
        )
    except InvalidUrgency:
        # Literal 422 sidesteps the status.HTTP_422_* deprecation rename.
        return _error(
            422,
            "URGENCY_TAG_REQUIRED_FOR_DISTRESS",
            "A distress sale requires an urgency tag (7_days, 14_days, or 30_days).",
        )

    return CreateListingResponse(listing_id=result.listing_id, status=result.status)


@router.post("/{listing_id}/save", response_model=SavedResponse)
async def save_listing(
    listing_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SavedListingService, Depends(get_saved_listing_service)],
) -> SavedResponse:
    """Save (favourite) a listing for the caller (SCRUM-95). Idempotent."""
    await service.save(buyer_id=current_user.user_id, listing_id=listing_id)
    return SavedResponse(listing_id=listing_id, saved=True)


@router.delete("/{listing_id}/save", response_model=SavedResponse)
async def unsave_listing(
    listing_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SavedListingService, Depends(get_saved_listing_service)],
) -> SavedResponse:
    """Remove a listing from the caller's saved list (SCRUM-95). Idempotent."""
    await service.unsave(buyer_id=current_user.user_id, listing_id=listing_id)
    return SavedResponse(listing_id=listing_id, saved=False)


@router.post("/{listing_id}/interest", response_model=ExpressInterestResponse)
async def express_interest(
    listing_id: UUID,
    body: ExpressInterestRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ExpressInterestService, Depends(get_express_interest_service)],
) -> ExpressInterestResponse:
    """Express interest in a listing (SCRUM-95) — lighter than an offer.
    Idempotent; the first interest bumps the listing's interest_count."""
    created = await service.express(
        buyer_id=current_user.user_id, listing_id=listing_id, message=body.message
    )
    return ExpressInterestResponse(listing_id=listing_id, new_interest=created)


@router.post("/{listing_id}/pause", response_model=ListingStatusResponse)
async def pause_listing(
    listing_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerListingsService, Depends(get_seller_listings_service)],
) -> ListingStatusResponse | JSONResponse:
    """Pause an active listing (hide it from the feed). Owner only (SCRUM-98)."""
    try:
        await service.pause(listing_id=listing_id, caller=current_user)
    except SellerListingNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found.")
    except SellerNotListingOwner:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_LISTING_OWNER", "This is not your listing.")
    except ListingNotPausable:
        return _error(422, "LISTING_NOT_PAUSABLE", "Only an active listing can be paused.")
    return ListingStatusResponse(id=listing_id, status="paused")


@router.post("/{listing_id}/resume", response_model=ListingStatusResponse)
async def resume_listing(
    listing_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerListingsService, Depends(get_seller_listings_service)],
) -> ListingStatusResponse | JSONResponse:
    """Resume a paused listing (return it to the feed). Owner only (SCRUM-98)."""
    try:
        await service.resume(listing_id=listing_id, caller=current_user)
    except SellerListingNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found.")
    except SellerNotListingOwner:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_LISTING_OWNER", "This is not your listing.")
    except ListingNotPausable:
        return _error(422, "LISTING_NOT_PAUSABLE", "Only a paused listing can be resumed.")
    return ListingStatusResponse(id=listing_id, status="active")


@router.patch("/{listing_id}", response_model=UpdateListingResponse)
async def update_listing(
    listing_id: UUID,
    body: UpdateListingRequest,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ListingUpdateService, Depends(get_listing_update_service)],
) -> UpdateListingResponse | JSONResponse:
    # exclude_unset distinguishes an omitted field (leave as-is) from an
    # explicit null (clear it); the service applies only what was sent.
    try:
        result = await service.update(
            listing_id=listing_id,
            caller=caller,
            changes=body.model_dump(exclude_unset=True),
        )
    except ListingNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
        )
    except NotListingOwner:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LISTING_OWNER",
            "You can only edit your own listings.",
        )
    except CannotEditSoldListing:
        return _error(422, "CANNOT_EDIT_SOLD_LISTING", "A sold listing can no longer be edited.")
    except InvalidUrgency:
        return _error(
            422,
            "URGENCY_TAG_REQUIRED_FOR_DISTRESS",
            "A distress sale requires an urgency tag (7_days, 14_days, or 30_days).",
        )

    return UpdateListingResponse(listing_id=result.listing_id, status=result.status)


@router.post(
    "/{listing_id}/media",
    status_code=status.HTTP_201_CREATED,
    response_model=MediaUploadResponse,
)
async def upload_media(
    listing_id: UUID,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[MediaUploadService, Depends(get_media_upload_service)],
    media_type: Annotated[MediaType, Form()],
    file: Annotated[UploadFile, File(description="Photo (JPEG/PNG) or video (MP4)")],
    sort_order: Annotated[int, Form(ge=0)] = 0,
) -> MediaUploadResponse | JSONResponse:
    # Read the bytes once; the service validates the magic-number type + size
    # server-side (the client content type/filename is not trusted).
    data = await file.read()
    try:
        result = await service.upload(
            listing_id=listing_id,
            caller=caller,
            media_type=media_type,
            data=data,
            sort_order=sort_order,
        )
    except ListingNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
        )
    except NotListingOwner:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LISTING_OWNER",
            "You can only add media to your own listings.",
        )
    except InvalidMedia as exc:
        # Never echo the media bytes. Literal 422 sidesteps the deprecation rename.
        return _error(422, exc.code, str(exc))
    except MediaLimitExceeded:
        return _error(
            422,
            "MEDIA_LIMIT_EXCEEDED",
            "This listing already has the maximum number of that media type.",
        )
    except MediaStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "MEDIA_STORAGE_UNAVAILABLE",
            "Media storage is temporarily unavailable. Please retry.",
        )

    return MediaUploadResponse(media_id=result.media_id, cdn_url=result.cdn_url)
