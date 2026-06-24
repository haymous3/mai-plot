"""/realtors routes — realtor onboarding (SCRUM-71).

POST /realtors lets a realtor-role user complete their profile (ESVARBON +
coverage + government-ID upload); GET /realtors/me returns the caller's profile.
Registration is multipart (the ID file + form fields).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_onboarding_service, get_realtor_repo
from app.repositories.realtor_repo import RealtorRepository
from app.schemas.realtor import RealtorProfile
from app.security import CurrentUser
from app.services.credentials import InvalidCredential
from app.services.realtor_onboarding import (
    AlreadyRegistered,
    NotRealtorRole,
    RealtorOnboardingService,
    StorageUnavailable,
)

router = APIRouter(prefix="/realtors", tags=["realtors"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OnboardingDep = Annotated[RealtorOnboardingService, Depends(get_onboarding_service)]
RealtorRepoDep = Annotated[RealtorRepository, Depends(get_realtor_repo)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def register_realtor(
    request: Request,
    caller: CurrentUserDep,
    service: OnboardingDep,
    file: UploadFile,
    esvarbon_number: Annotated[str, Form()],
    coverage_states: Annotated[list[str], Form()],
    years_of_experience: Annotated[int | None, Form()] = None,
    coverage_lgas: Annotated[list[str], Form()] = [],  # noqa: B006 — FastAPI Form default
    base_lat: Annotated[float | None, Form()] = None,
    base_lng: Annotated[float | None, Form()] = None,
) -> RealtorProfile | JSONResponse:
    """Complete the caller's realtor profile → approval_status 'pending'. An
    optional base_lat/base_lng records the realtor's location for auto-assignment
    (SCRUM-72)."""
    data = await file.read()
    try:
        realtor = await service.register(
            user_id=caller.user_id,
            role=caller.role,
            esvarbon_number=esvarbon_number,
            years_of_experience=years_of_experience,
            coverage_states=coverage_states,
            coverage_lgas=coverage_lgas,
            id_document=data,
            base_lat=base_lat,
            base_lng=base_lng,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except NotRealtorRole:
        return _error(status.HTTP_403_FORBIDDEN, "REALTOR_ROLE_REQUIRED", "Realtor role required.")
    except AlreadyRegistered:
        return _error(
            status.HTTP_409_CONFLICT,
            "REALTOR_ALREADY_REGISTERED",
            "A realtor application already exists for this account.",
        )
    except InvalidCredential as exc:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code, str(exc))
    except StorageUnavailable:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STORAGE_UNAVAILABLE",
            "Document storage is temporarily unavailable. Please retry.",
        )
    return RealtorProfile.from_row(realtor)


@router.get("/me", response_model=None)
async def get_my_profile(
    caller: CurrentUserDep, realtors: RealtorRepoDep
) -> RealtorProfile | JSONResponse:
    """The caller's realtor profile, or 404 if they haven't registered."""
    realtor = await realtors.get(caller.user_id)
    if realtor is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "REALTOR_NOT_FOUND", "No realtor profile for this account."
        )
    return RealtorProfile.from_row(realtor)
