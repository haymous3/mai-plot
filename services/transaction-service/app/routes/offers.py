"""Seller Offers inbox route (SCRUM-98).

GET /offers lists every offer on the caller's listings. The accept/counter/reject
actions stay on /transactions/{offer_id}/... (SCRUM-66).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_seller_offers_service
from app.schemas.offer import SellerOffersResponse
from app.security import CurrentUser
from app.services.seller_offers import SellerOffersService

router = APIRouter(prefix="/offers", tags=["offers"])


@router.get("", response_model=SellerOffersResponse)
async def list_offers(
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerOffersService, Depends(get_seller_offers_service)],
) -> SellerOffersResponse:
    """Every offer on the caller's listings, newest first."""
    return await service.list_for_seller(caller.user_id)
