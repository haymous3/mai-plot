"""/listings route handlers.

Handlers are thin: build the Pydantic request, call the service, translate
domain errors to HTTP responses matching api-contracts.md. No DB calls here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_listing_create_service
from app.schemas.listing import CreateListingRequest, CreateListingResponse
from app.security import CurrentUser
from app.services.listing_create import (
    BvnRequired,
    CreateListingInput,
    InvalidUrgency,
    ListingCreateService,
    NotSeller,
)
from app.services.poa_guard import PoaNotVerified

router = APIRouter(prefix="/listings", tags=["listings"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


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
