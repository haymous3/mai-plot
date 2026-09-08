"""/admin/transactions — the deal picker behind manual inspection assignment
(SCRUM-213).

An admin placing an inspection has to choose WHICH deal. Nothing listed deals for
an admin before this: `/admin/escrow/{transaction_id}` needs an id you already
have, and the buyer/seller deal lists are caller-scoped.

⚠️ `/admin/transactions` is a NEW Kong prefix and is added to
infra/kong/kong.yml in this same ticket. Seven tickets have been lost to an
endpoint that worked on the service port and 404'd at the gateway.

Gated by require_admin (admin JWT + IP allowlist), like every admin route here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import SessionDep, require_admin
from app.repositories.transaction_repo import TransactionRepository
from app.schemas.admin_deals import AdminDealItem, AdminDealsResponse, Pagination
from app.security import CurrentUser

router = APIRouter(prefix="/admin/transactions", tags=["admin-transactions"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]


@router.get("", response_model=AdminDealsResponse)
async def list_deals(
    _admin: AdminDep,
    session: SessionDep,
    search: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminDealsResponse:
    """Live deals, newest first. `search` matches the property title or a full
    transaction id.

    Completed and cancelled deals are excluded — an inspection on a finished deal
    is never the intent, and including them would bury the actionable ones.
    """
    items, total = await TransactionRepository(session).list_for_admin(
        search=search, page=page, page_size=page_size
    )
    return AdminDealsResponse(
        items=[AdminDealItem.from_row(row) for row in items],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )
