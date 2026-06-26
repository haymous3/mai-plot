"""Admin loan/repayment view (SCRUM-77). GET /admin/loans — admin only.

Lists decided loans with their repayment rollup (paid / overdue counts, totals)
so the admin dashboard can show active loans and repayment status. require_admin =
admin JWT AND (if configured) the IP allowlist.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_repayment_query_service, require_admin
from app.schemas.repayment import ActiveLoanOut, ActiveLoansOut
from app.security import CurrentUser
from app.services.repayment_query import RepaymentQueryService

router = APIRouter(prefix="/admin/loans", tags=["admin-loans"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
RepaymentsDep = Annotated[RepaymentQueryService, Depends(get_repayment_query_service)]


@router.get("", response_model=ActiveLoansOut)
async def list_active_loans(
    _admin: AdminDep,
    service: RepaymentsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActiveLoansOut:
    items = await service.list_active(limit=limit, offset=offset)
    return ActiveLoansOut(items=[ActiveLoanOut.from_item(i) for i in items])
