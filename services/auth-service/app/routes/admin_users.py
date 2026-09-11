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

from app.dependencies import get_admin_nin_service, get_admin_user_service, require_admin
from app.schemas.admin_users import (
    AdminNinClearRequest,
    AdminNinRevealRequest,
    AdminNinRevealResponse,
    AdminNinSetRequest,
    AdminNinStatusResponse,
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
from app.services import admin_nin
from app.services.admin_nin import AdminNinService, NinStatus
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
from app.services.nin import InvalidNinError

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]
NinServiceDep = Annotated[AdminNinService, Depends(get_admin_nin_service)]


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


# --- NIN console (SCRUM-224) -------------------------------------------------
#
# Four endpoints under the same /admin/users prefix (so Kong already routes
# them): masked status, audited reveal, set/replace, clear. The detail response
# above still carries only `nin_verified`; the number itself exists in exactly
# one response, the reveal, and every reveal writes an audit row with the
# admin's stated reason. See services/admin_nin.py for the protections.


def _nin_status(status_: NinStatus) -> AdminNinStatusResponse:
    return AdminNinStatusResponse(
        nin_verified=status_.nin_verified,
        nin_last4=status_.nin_last4,
        nin_verified_at=status_.nin_verified_at,
        recoverable=status_.recoverable,
    )


def _nin_error(exc: admin_nin.AdminNinError) -> JSONResponse:
    """The error mapping shared by the four NIN handlers."""
    match exc:
        case admin_nin.UserNotFound():
            return _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "No such user.")
        case admin_nin.UserDeleted():
            return _error(
                status.HTTP_409_CONFLICT,
                "USER_DELETED",
                "This account is deleted; its NIN can be revealed but not changed.",
            )
        case admin_nin.NinNotOnFile():
            return _error(status.HTTP_404_NOT_FOUND, "NIN_NOT_ON_FILE", "No NIN on file.")
        case admin_nin.NinNotRecoverable():
            return _error(
                status.HTTP_409_CONFLICT,
                "NIN_NOT_RECOVERABLE",
                "This NIN was verified before recoverable storage existed and cannot be "
                "shown. Replace it to store a recoverable copy.",
            )
        case admin_nin.NinBelongsToAnotherAccount():
            return _error(
                status.HTTP_409_CONFLICT,
                "NIN_BELONGS_TO_ANOTHER_ACCOUNT",
                "Another account already holds this NIN.",
            )
        case admin_nin.NinRejectedByRegistry():
            return JSONResponse(
                status_code=422,
                content={
                    "error_code": "NIN_NOT_VERIFIED",
                    "message": "The registry did not confirm this NIN for this person.",
                    "details": {"status": exc.status, "mismatches": list(exc.mismatches)},
                },
            )
        case admin_nin.NinRegistryUnavailable():
            return _error(
                status.HTTP_502_BAD_GATEWAY,
                "NIN_VERIFICATION_UNAVAILABLE",
                "NIN verification is temporarily unavailable. Please retry.",
            )
    raise exc  # pragma: no cover - every subclass is matched above


@router.get("/{user_id}/nin", response_model=None)
async def get_user_nin(
    user_id: UUID,
    admin: AdminDep,
    service: NinServiceDep,
) -> AdminNinStatusResponse | JSONResponse:
    """Masked NIN status: verified?, last four digits, when, and whether a
    reveal would work. Never the number — that is the POST below."""
    try:
        return _nin_status(await service.get_status(user_id=user_id))
    except admin_nin.AdminNinError as exc:
        return _nin_error(exc)


@router.post("/{user_id}/nin/reveal", response_model=None)
async def reveal_user_nin(
    user_id: UUID,
    payload: AdminNinRevealRequest,
    request: Request,
    admin: AdminDep,
    service: NinServiceDep,
) -> AdminNinRevealResponse | JSONResponse:
    """Return the NIN in full. AUDITED (`user.nin_revealed_by_admin`) with the
    mandatory reason; the audit row and the decrypt share one transaction, so
    there is no reveal without a record of it.

    A POST rather than a GET on purpose: reading a national identity number is
    an act with a reason attached, not a resource to be fetched, cached or
    prefetched. Works on a deleted account — a regulator request does not stop
    at deletion.
    """
    try:
        nin = await service.reveal(
            user_id=user_id,
            admin=admin,
            reason=payload.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except admin_nin.AdminNinError as exc:
        return _nin_error(exc)
    return AdminNinRevealResponse(nin=nin, nin_last4=nin[-4:])


@router.put("/{user_id}/nin", response_model=None)
async def set_user_nin(
    user_id: UUID,
    payload: AdminNinSetRequest,
    request: Request,
    admin: AdminDep,
    service: NinServiceDep,
) -> AdminNinStatusResponse | JSONResponse:
    """Create or replace the NIN. Re-verified with the registry first — an
    admin cannot put an unconfirmed number on file — and refused with 409 if
    another account already holds it. AUDITED (`user.nin_set_by_admin`) with
    the old and new last-4 and the reason."""
    try:
        status_ = await service.set_nin(
            user_id=user_id,
            admin=admin,
            nin=payload.nin,
            reason=payload.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidNinError:
        # Never echo the value. Literal 422 sidesteps the status.HTTP_422_*
        # deprecation rename (see main.py).
        return _error(422, "NIN_FORMAT_INVALID", "NIN must be exactly 11 digits.")
    except admin_nin.AdminNinError as exc:
        return _nin_error(exc)
    return _nin_status(status_)


@router.delete("/{user_id}/nin", response_model=None)
async def clear_user_nin(
    user_id: UUID,
    payload: AdminNinClearRequest,
    request: Request,
    admin: AdminDep,
    service: NinServiceDep,
) -> AdminNinStatusResponse | JSONResponse:
    """Remove the NIN. `verified_status` walks back from `id_verified` to the
    phone/email rung unless a BVN is still on file, so a cleared account cannot
    keep passing identity gates. The user may verify again through onboarding afterwards. AUDITED
    (`user.nin_cleared_by_admin`)."""
    try:
        status_ = await service.clear_nin(
            user_id=user_id,
            admin=admin,
            reason=payload.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except admin_nin.AdminNinError as exc:
        return _nin_error(exc)
    return _nin_status(status_)
