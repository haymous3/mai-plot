"""/inspections routes — request/accept (SCRUM-72) + report submit/view (SCRUM-73).

A transaction party requests an inspection (auto-assigned to the nearest approved
realtor); the assigned realtor accepts within the 2-hour window, then submits a
GPS-stamped report with photos. The report is viewable by the parties + admin.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_current_user,
    get_inspection_service,
    get_report_service,
)
from app.schemas.inspection import (
    AssignedRealtorResponse,
    InspectionRequest,
    InspectionResponse,
    ProposeTimeRequest,
    RealtorInspectionsResponse,
)
from app.schemas.report import ReportResponse, ReportSubmitResponse
from app.security import CurrentUser
from app.services.credentials import InvalidCredential
from app.services.inspection_service import (
    AssignmentExpired,
    InspectionAlreadyActive,
    InspectionNotFound,
    InspectionNotPending,
    InspectionService,
    InvalidProposedTime,
    NoRealtorAvailable,
    NotAssignedRealtor,
    NotTransactionParty,
    TransactionNotFound,
)
from app.services.report_service import (
    GpsOutOfRange,
    NotAuthorizedForReport,
    ReportError,
    ReportNotFound,
    ReportNotSubmittable,
    ReportService,
    ReportTooEarly,
)

router = APIRouter(prefix="/inspections", tags=["inspections"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
InspectionServiceDep = Annotated[InspectionService, Depends(get_inspection_service)]
ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


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


@router.get("/mine", response_model=RealtorInspectionsResponse)
async def my_inspections(
    caller: CurrentUserDep, service: InspectionServiceDep
) -> RealtorInspectionsResponse:
    """The calling realtor's assigned inspections, newest first — the realtor
    portal's dashboard + assigned-inspections feed (SCRUM-140)."""
    rows = await service.list_for_realtor(caller=caller)
    return RealtorInspectionsResponse.from_rows(rows)


@router.get("/by-transaction/{transaction_id}", response_model=None)
async def assigned_realtor(
    transaction_id: UUID, caller: CurrentUserDep, service: InspectionServiceDep
) -> AssignedRealtorResponse | JSONResponse:
    """The realtor assigned to a transaction's inspection, for the buyer/seller
    transaction view (SCRUM-139). Name + ESVARBON + inspection status only."""
    try:
        row = await service.assigned_realtor_for_transaction(
            caller=caller, transaction_id=transaction_id
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No such transaction.")
    except NotTransactionParty:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_TRANSACTION_PARTY",
            "Only the buyer or seller can view the assigned realtor.",
        )
    return AssignedRealtorResponse.none() if row is None else AssignedRealtorResponse.from_row(row)


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


@router.post("/{inspection_id}/propose-time", response_model=None)
async def propose_inspection_time(
    inspection_id: UUID,
    payload: ProposeTimeRequest,
    caller: CurrentUserDep,
    service: InspectionServiceDep,
) -> InspectionResponse | JSONResponse:
    """The assigned realtor proposes an alternate time (instead of accepting the
    proposed one) within the 2-hour window — moves the inspection to 'rescheduled'
    and notifies the transaction parties."""
    try:
        inspection = await service.propose_time(
            caller=caller, inspection_id=inspection_id, new_date=payload.proposed_date
        )
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
    except InvalidProposedTime:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_PROPOSED_TIME",
            "The proposed time must be in the future.",
        )
    return InspectionResponse.from_row(inspection)


@router.post("/{inspection_id}/report", response_model=None, status_code=status.HTTP_201_CREATED)
async def submit_report(
    inspection_id: UUID,
    request: Request,
    caller: CurrentUserDep,
    service: ReportServiceDep,
    photos: list[UploadFile],
    gps_lat: Annotated[float, Form()],
    gps_lng: Annotated[float, Form()],
    property_condition: Annotated[str, Form()],
    amenities: Annotated[list[str], Form()] = [],  # noqa: B006 — FastAPI Form default
    discrepancies: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
) -> ReportSubmitResponse | JSONResponse:
    """The assigned realtor submits a GPS-stamped report with >=3 photos."""
    photo_bytes = [await p.read() for p in photos]
    try:
        inspection = await service.submit(
            caller=caller,
            inspection_id=inspection_id,
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            property_condition=property_condition,
            amenities=amenities,
            discrepancies=discrepancies,
            remarks=remarks,
            photos=photo_bytes,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InspectionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND", "No such inspection.")
    except NotAssignedRealtor:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_ASSIGNED_REALTOR",
            "This inspection is not assigned to you.",
        )
    except ReportNotSubmittable:
        return _error(
            status.HTTP_409_CONFLICT,
            "REPORT_NOT_SUBMITTABLE",
            "The inspection must be accepted and not already reported.",
        )
    except ReportTooEarly:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "REPORT_TOO_EARLY",
            "The report cannot be submitted before the confirmed inspection date.",
        )
    except GpsOutOfRange:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "GPS_OUT_OF_RANGE",
            "The GPS location is not within range of the property.",
        )
    except InvalidCredential as exc:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code, str(exc))
    except ReportError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STORAGE_UNAVAILABLE",
            "Photo storage is temporarily unavailable. Please retry.",
        )
    return ReportSubmitResponse.from_row(inspection)


@router.get("/{inspection_id}/report", response_model=None)
async def view_report(
    inspection_id: UUID, caller: CurrentUserDep, service: ReportServiceDep
) -> ReportResponse | JSONResponse:
    """View a submitted report (buyer, seller, admin, or the assigned realtor)."""
    try:
        view = await service.get_report(caller=caller, inspection_id=inspection_id)
    except InspectionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND", "No such inspection.")
    except NotAuthorizedForReport:
        return _error(status.HTTP_403_FORBIDDEN, "NOT_AUTHORIZED", "You may not view this report.")
    except ReportNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "REPORT_NOT_FOUND", "No report has been submitted yet."
        )
    return ReportResponse.from_view(view)
