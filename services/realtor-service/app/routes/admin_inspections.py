"""/admin/inspections placement routes (SCRUM-208).

The queue of inspection requests nobody could be assigned to, plus the two ways
an admin resolves one: place a waiting request with a chosen realtor, or create
an assignment outright.

Why this exists: assignment was proximity-only with no human in the loop, and a
request that found nobody in range 503'd and was gone. An admin could not place
an inspection at all — `POST /inspections` is party-gated, and an admin is not a
party to the transaction.

Mounted on the SAME `/admin/inspections` prefix as the report-review routes
(admin_reports.py), so Kong's existing `admin-inspections` route covers these
with no gateway change — the individual-paths trap has cost six tickets, and the
cheapest way to avoid a seventh is to not invent a new prefix.

Gated by require_admin (admin JWT + IP allowlist), like every other admin route
here.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_admin_inspection_service, require_admin
from app.schemas.admin_inspection import (
    AdminCreateInspectionRequest,
    AdminInspectionResponse,
    AssignableRealtorItem,
    AssignableRealtorsResponse,
    PlaceInspectionRequest,
    UnassignedInspectionItem,
    UnassignedInspectionsResponse,
)
from app.security import CurrentUser
from app.services.admin_inspection_service import (
    AdminInspectionService,
    InspectionAlreadyActive,
    InspectionNotFound,
    InspectionNotUnassigned,
    InvalidProposedDate,
    NoRealtorInRange,
    RealtorNotAssignable,
    TransactionNotFound,
)

router = APIRouter(prefix="/admin/inspections", tags=["admin-inspection-placement"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ServiceDep = Annotated[AdminInspectionService, Depends(get_admin_inspection_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/unassigned", response_model=UnassignedInspectionsResponse)
async def unassigned_queue(
    admin: AdminDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> UnassignedInspectionsResponse:
    """Inspection requests still waiting for a realtor, oldest first."""
    rows = await service.list_unassigned(limit=limit)
    return UnassignedInspectionsResponse(items=[UnassignedInspectionItem.from_row(r) for r in rows])


@router.get("/assignable-realtors", response_model=AssignableRealtorsResponse)
async def assignable_realtors(
    admin: AdminDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AssignableRealtorsResponse:
    """Approved realtors the admin may place work with — the picker source.

    Not `/admin/realtors/queue`, which is pending applications only: before this
    the admin UI had nothing to choose from.
    """
    rows = await service.list_assignable_realtors(limit=limit)
    return AssignableRealtorsResponse(items=[AssignableRealtorItem.from_row(r) for r in rows])


@router.post("/{inspection_id}/assign", response_model=None)
async def assign_inspection(
    inspection_id: UUID,
    payload: PlaceInspectionRequest,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminInspectionResponse | JSONResponse:
    """Place a waiting inspection with a chosen approved realtor.

    The 50km radius is deliberately NOT applied: `find_nearest_approved` needs a
    `base_location`, onboarding collects none, so every realtor who signed up
    through the product is invisible to proximity. Manual placement is the only
    route to them, and inheriting that filter would defeat the endpoint.
    Approval, by contrast, IS still required — an unvetted person must not be
    sent to a property to meet a buyer.
    """
    try:
        placed = await service.place(
            inspection_id=inspection_id,
            realtor_id=payload.realtor_id,
            admin=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InspectionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND", "No such inspection.")
    except InspectionNotUnassigned:
        return _error(
            status.HTTP_409_CONFLICT,
            "INSPECTION_NOT_UNASSIGNED",
            "This inspection already has a realtor.",
        )
    except RealtorNotAssignable:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "REALTOR_NOT_ASSIGNABLE",
            "That realtor does not exist or is not approved.",
        )
    return AdminInspectionResponse.from_row(placed)


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    payload: AdminCreateInspectionRequest,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> AdminInspectionResponse | JSONResponse:
    """Create an inspection for a transaction on the admin's authority.

    With `realtor_id`, that realtor is assigned. Without it, proximity is tried
    and answers 503 if nobody is in range — unlike the buyer/seller path, which
    records an unassigned request, because an admin who asked us to choose is
    owed the answer rather than a row that is still waiting.
    """
    try:
        result = await service.create(
            transaction_id=payload.transaction_id,
            proposed_date=payload.proposed_date,
            realtor_id=payload.realtor_id,
            admin=admin,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No such transaction.")
    except InspectionAlreadyActive:
        return _error(
            status.HTTP_409_CONFLICT,
            "INSPECTION_ALREADY_ACTIVE",
            "This transaction already has a live inspection.",
        )
    except InvalidProposedDate:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "PROPOSED_DATE_INVALID",
            "The proposed inspection date must be in the future.",
        )
    except RealtorNotAssignable:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "REALTOR_NOT_ASSIGNABLE",
            "That realtor does not exist or is not approved.",
        )
    except NoRealtorInRange:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "NO_REALTOR_IN_RANGE",
            "No approved realtor with a base location is within range. Choose one manually.",
        )
    return AdminInspectionResponse.from_row(result.inspection, auto_assigned=result.auto_assigned)
