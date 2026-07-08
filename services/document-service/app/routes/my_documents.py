"""Seller Documents list route — GET /documents/mine (SCRUM-98).

Lists every document across the caller's listings. The file bytes are served
only via the watermarked view route (/documents/{id}/view).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_seller_documents_service
from app.schemas.document import SellerDocumentsResponse
from app.security import CurrentUser
from app.services.seller_documents import SellerDocumentsService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/mine", response_model=SellerDocumentsResponse)
async def list_my_documents(
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerDocumentsService, Depends(get_seller_documents_service)],
) -> SellerDocumentsResponse:
    """Every document on the caller's listings, newest first."""
    return await service.list_for_seller(caller.user_id)
