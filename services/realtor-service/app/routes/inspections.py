"""/inspections routes — request + accept (SCRUM-72).

A transaction party requests an inspection (auto-assigned to the nearest approved
realtor); the assigned realtor accepts within the 2-hour window.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_inspection_service
from app.schemas.inspection import InspectionRequest, InspectionResponse
from app.security import CurrentUser
from app.services.inspection_service import (
    AssignmentExpired,
    InspectionAlreadyActive,
    InspectionNotFound,
    InspectionNotPending,
    InspectionService,
    NoRealtorAvailable,
    NotAssignedRealtor,
    NotTransactionParty,
    TransactionNotFound,
)

router = APIRouter(prefix="/inspections", tags=["inspections"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
InspectionServiceDep = Annotated[InspectionService, Depends(get_inspection_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def request_inspection(
    payload: InspectionRequest, caller: CurrentUserDep, service: InspectionServiceDep
) -> InspectionResponse | JSONResponse:
    """Request an inspection for a transaction → auto-assigns the nearest realtor."""
    try:
        inspection = await service.request(
            caller=caller,
            transaction_id=payload.transaction_id,
            proposed_date=payload.proposed_date,
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No such transaction.")
    except NotTransactionParty:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_TRANSACTION_PARTY",
            "Only the buyer or seller can request an inspection.",
        )
    except InspectionAlreadyActive:
        return _error(
            status.HTTP_409_CONFLICT,
            "INSPECTION_ALREADY_ACTIVE",
            "This transaction already has an active inspection.",
        )
    except NoRealtorAvailable:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "NO_REALTOR_AVAILABLE",
            "No realtor is available in range. An admin has been alerted.",
        )
    return InspectionResponse.from_row(inspection)


@router.post("/{inspection_id}/accept", response_model=None)
async def accept_inspection(
    inspection_id: UUID, caller: CurrentUserDep, service: InspectionServiceDep
) -> InspectionResponse | JSONResponse:
    """The assigned realtor accepts the inspection within the 2-hour window."""
    try:
        inspection = await service.accept(caller=caller, inspection_id=inspection_id)
    except InspectionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND", "No such inspection.")
    except NotAssignedRealtor:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_ASSIGNED_REALTOR",
            "This inspection is not assigned to you.",
        )
    except InspectionNotPending:
        return _error(
            status.HTTP_409_CONFLICT,
            "INSPECTION_NOT_PENDING",
            "This inspection is not awaiting acceptance.",
        )
    except AssignmentExpired:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ASSIGNMENT_EXPIRED",
            "The 2-hour acceptance window has elapsed.",
        )
    return InspectionResponse.from_row(inspection)
