"""Admin escrow endpoints (SCRUM-69).

Read a transaction's escrow ledger + balance, and apply the second approval to a
dual-approval disbursement. Both require an admin JWT AND a whitelisted IP
(require_admin). Recording credits/debits is done by the payment flow (M3) via
EscrowLedgerService, not exposed as an endpoint.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_escrow_service, require_admin
from app.schemas.escrow import ApproveResponse, EscrowLedgerResponse, LedgerEntry
from app.security import CurrentUser
from app.services.escrow_ledger import EscrowLedgerService, NoPendingApproval, SameApprover

router = APIRouter(prefix="/admin/escrow", tags=["escrow"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
EscrowServiceDep = Annotated[EscrowLedgerService, Depends(get_escrow_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/{transaction_id}", response_model=EscrowLedgerResponse)
async def get_ledger(
    transaction_id: UUID,
    _admin: AdminDep,
    service: EscrowServiceDep,
) -> EscrowLedgerResponse:
    """The escrow ledger + running balance for a transaction."""
    balance = await service.balance(transaction_id)
    entries = await service.list_entries(transaction_id)
    return EscrowLedgerResponse(
        transaction_id=transaction_id,
        balance_kobo=balance.balance_kobo,
        pending_kobo=balance.pending_kobo,
        entries=[
            LedgerEntry(
                id=e.id,
                transaction_id=e.transaction_id,
                entry_type=e.entry_type,
                amount_kobo=e.amount_kobo,
                description=e.description,
                payment_event_id=e.payment_event_id,
                requires_dual_approval=e.requires_dual_approval,
                approved_by_1=e.approved_by_1,
                approved_by_2=e.approved_by_2,
                approved_at=e.approved_at,
                effective=e.effective,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )


@router.post("/{payment_event_id}/approve", response_model=ApproveResponse)
async def approve(
    payment_event_id: UUID,
    request: Request,
    admin: AdminDep,
    service: EscrowServiceDep,
) -> ApproveResponse | JSONResponse:
    """Second approval for a dual-approval disbursement. Must be a different
    admin than the one who initiated it (CLAUDE.md rule §9)."""
    try:
        approved = await service.second_approval(
            payment_event_id=payment_event_id,
            approver=admin.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except NoPendingApproval:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NO_PENDING_APPROVAL",
            "No disbursement is awaiting a second approval for this payment.",
        )
    except SameApprover:
        return _error(
            status.HTTP_409_CONFLICT,
            "DUAL_APPROVAL_SAME_ADMIN",
            "The second approval must come from a different admin.",
        )
    return ApproveResponse(
        payment_event_id=payment_event_id, status="approved", approved_entry_ids=approved
    )
