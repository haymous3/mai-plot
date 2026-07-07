"""Seller Transactions ("sales") route (SCRUM-98).

GET /sales lists the caller's transactions as the seller. The buyer-side deals
list stays on GET /transactions (SCRUM-95); this is the seller's mirror.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_seller_deals_service
from app.schemas.transaction import SellerDealsResponse
from app.security import CurrentUser
from app.services.seller_deals import SellerDealsService

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("", response_model=SellerDealsResponse)
async def list_sales(
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerDealsService, Depends(get_seller_deals_service)],
) -> SellerDealsResponse:
    """The caller's transactions as the seller, newest first."""
    return await service.list_for_seller(caller.user_id)
