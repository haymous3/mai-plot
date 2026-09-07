"""/internal routes — service-to-service calls (SCRUM-209).

One endpoint: whether a GIVEN user is a party to a live deal. auth-service's
admin console needs it before soft-deleting somebody else's account.

Why this exists when `/transactions/active-deals` already does
--------------------------------------------------------------
That one is CALLER-scoped: it reads the subject from the JWT, which is exactly
right for a user deleting their own account (auth-service forwards the user's own
token and no service credential is needed). It is exactly WRONG for an admin
deleting someone else — with an admin's token it answers "does the ADMIN have
deals", so the guard would pass while the target's escrow was still in motion.
A guard that checks the wrong subject is worse than no guard: it reads as
protection and provides none.

⚠️ NOT ROUTED THROUGH KONG. `infra/kong/kong.yml` lists public paths
individually and /internal is deliberately absent; transaction-service is a
private service. Authentication is the admin's own forwarded token, checked for
ROLE only — `require_admin_service_call`, not `require_admin` — because the
request arrives from auth-service's address, never the admin's browser, so an IP
allowlist would check the wrong machine. Same reasoning, same shape, as
auth-service's own /internal route (SCRUM-207).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import SessionDep, require_admin_service_call
from app.repositories.transaction_repo import TransactionRepository
from app.schemas.transaction import ActiveDealsResponse
from app.security import CurrentUser

router = APIRouter(prefix="/internal", tags=["internal"])

AdminDep = Annotated[CurrentUser, Depends(require_admin_service_call)]


@router.get("/users/{user_id}/active-deals", response_model=ActiveDealsResponse)
async def user_active_deals(
    user_id: UUID,
    admin: AdminDep,
    session: SessionDep,
) -> ActiveDealsResponse:
    """Whether THIS user is a party to any non-terminal deal.

    Role-agnostic: `count_active_for_party` matches buyer, seller or realtor, so
    one query answers for every role. 'disputed' counts as active — a dispute is
    precisely when an account must not vanish.
    """
    count = await TransactionRepository(session).count_active_for_party(user_id)
    return ActiveDealsResponse(active_count=count, has_active=count > 0)
