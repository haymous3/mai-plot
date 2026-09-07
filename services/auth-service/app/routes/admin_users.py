"""/admin/users routes — the admin user console (SCRUM-209).

Find an account, read it, correct its profile, suspend it, or delete it. Before
this, no admin surface could show a USER at all: every queue is a queue of things,
so an admin could review a seller's power of attorney without being able to look
up the seller.

Gated by `require_admin` — admin JWT AND the IP allowlist, per §4. Note this is
NOT `require_admin_service_call`, the role-only gate the /internal route uses:
these endpoints are reached by a browser, so the allowlist applies and the names
are deliberately different so the wrong one cannot be picked by accident.

⚠️ `/admin/users` is a NEW Kong prefix. It is added to infra/kong/kong.yml in
this same ticket — six tickets have been lost to an endpoint that worked on the
service port and 404'd at the gateway.

The legal-team PoA queue lives in routes/admin.py on the same `/admin` prefix but
a different role gate; they are separate surfaces for separate jobs and are kept
in separate modules.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_admin_user_service, require_admin
from app.schemas.admin_users import (
    AdminUserDeleteRequest,
    AdminUserDeleteResponse,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserSuspendRequest,
    AdminUserUpdateRequest,
    Pagination,
    UserRoleFilter,
)
from app.security import CurrentUser, parse_bearer
from app.services.admin_users import (
    AdminUserService,
    AlreadyDeleted,
    CannotDeleteSelf,
    CannotDeleteStaff,
    DeleteCheckUnavailable,
    NothingToUpdate,
    UserHasActiveDeals,
    UserNotFound,
)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    admin: AdminDep,
    service: ServiceDep,
    role: UserRoleFilter | None = None,
    search: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
    include_deleted: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminUserListResponse:
    """Users, newest first. `role` filters; `search` matches name, email or phone.

    A 2-character minimum on `search`: a single character matches most of the
    table, which is a slow scan returning something useless.

    Soft-deleted accounts are hidden unless `include_deleted=true` — they are the
    exception, and looking for one is deliberate.
    """
    result = await service.list_users(
        role=role,
        search=search,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(
        items=[AdminUserListItem.from_row(row) for row in result.items],
        pagination=Pagination(page=page, page_size=page_size, total=result.total),
    )


@router.get("/{user_id}", response_model=None)
async def get_user(
    user_id: UUID,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminUserDetailResponse | JSONResponse:
    """One account in full. The read is AUDITED (`user.viewed_by_admin`).

    Returns a soft-deleted or suspended account rather than 404: an admin looking
    one up is usually asking what happened to it, and hiding the deleted ones
    hides the answer.
    """
    try:
        detail = await service.get_user(
            user_id=user_id,
            admin=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
    return AdminUserDetailResponse.from_detail(detail)


@router.patch("/{user_id}", response_model=None)
async def update_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminUserDetailResponse | JSONResponse:
    """Correct a user's profile text: name, location, address.

    Role, email and phone are NOT editable here and a request carrying them is
    not rejected — the fields are ignored. Role is a privilege-escalation path;
    email and phone are verified identifiers whose silent change transfers
    account ownership and breaks a realtor's MH-R sign-in.
    """
    try:
        detail = await service.update_profile(
            user_id=user_id,
            admin=admin,
            full_name=payload.full_name,
            location=payload.location,
            set_location=payload.sent_location,
            address=payload.address,
            set_address=payload.sent_address,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
    except NothingToUpdate:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NOTHING_TO_UPDATE",
            "Send at least one of full_name, location or address.",
        )
    return AdminUserDetailResponse.from_detail(detail)


@router.post("/{user_id}/suspend", response_model=None)
async def suspend_user(
    user_id: UUID,
    payload: AdminUserSuspendRequest,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminUserDetailResponse | JSONResponse:
    """Suspend an account: no new logins, and every existing session revoked.

    Revoking matters — leaving current tokens alive until they expire would make
    "suspended" mean "suspended in fifteen minutes", which is not what an admin
    pressing this button means.
    """
    try:
        detail = await service.set_active(
            user_id=user_id,
            active=False,
            admin=admin,
            reason=payload.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
    except AlreadyDeleted:
        return _error(
            status.HTTP_409_CONFLICT,
            "USER_DELETED",
            "This account is deleted; it cannot be suspended.",
        )
    return AdminUserDetailResponse.from_detail(detail)


@router.post("/{user_id}/reactivate", response_model=None)
async def reactivate_user(
    user_id: UUID,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminUserDetailResponse | JSONResponse:
    """Lift a suspension. No reason required: restoring access is the safe
    direction, and the audit row already names who did it."""
    try:
        detail = await service.set_active(
            user_id=user_id,
            active=True,
            admin=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
    except AlreadyDeleted:
        return _error(
            status.HTTP_409_CONFLICT,
            "USER_DELETED",
            "This account is deleted; reactivating it is not possible here.",
        )
    return AdminUserDetailResponse.from_detail(detail)


@router.delete("/{user_id}", response_model=None)
async def delete_user(
    user_id: UUID,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
    payload: AdminUserDeleteRequest | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminUserDeleteResponse | JSONResponse:
    """Soft-delete an account.

    Soft because `audit_log` has append-only triggers and an FK to `users`, so a
    user who ever caused an audit row cannot be removed — and CBN/AMLON need the
    financial trail regardless. Sessions are revoked and the email + phone are
    released for reuse by the partial unique indexes (migrations 0009/0010).

    **503 means nothing was deleted.** The active-deals guard is fail-closed: an
    unreachable transaction-service means "unknown", and deleting an account whose
    escrow we could not check is not recoverable through the product, whereas
    asking the admin to retry in a minute is.

    The admin's own token is forwarded to transaction-service, which answers about
    the TARGET (`/internal/users/{id}/active-deals`) rather than about the caller.
    """
    try:
        await service.delete_user(
            user_id=user_id,
            admin=admin,
            bearer_token=parse_bearer(authorization),
            reason=payload.reason if payload else None,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UserNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
    except AlreadyDeleted:
        return _error(status.HTTP_409_CONFLICT, "USER_ALREADY_DELETED", "Already deleted.")
    except CannotDeleteStaff:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "CANNOT_DELETE_STAFF",
            "Admin and legal-team accounts are managed outside this console.",
        )
    except CannotDeleteSelf:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "CANNOT_DELETE_SELF",
            "You cannot delete your own account here.",
        )
    except UserHasActiveDeals:
        return _error(
            status.HTTP_409_CONFLICT,
            "USER_HAS_ACTIVE_DEALS",
            "This user still has a deal in progress. It must be completed or cancelled first.",
        )
    except DeleteCheckUnavailable:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DELETE_CHECK_UNAVAILABLE",
            "Could not confirm this user has no deals in progress. Nothing was deleted — "
            "please try again shortly.",
        )
    return AdminUserDeleteResponse(message="The account has been deleted.")
