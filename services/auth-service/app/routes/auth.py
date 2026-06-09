"""/auth route handlers.

Handlers are thin: build a Pydantic request, call the service, translate
domain errors to HTTP responses matching api-contracts.md. No DB calls
here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import get_otp_verification_service, get_registration_service
from app.schemas.auth import (
    OtpVerifyRequest,
    OtpVerifyResponse,
    RegisterRequest,
    RegisterResponse,
    UserPublic,
)
from app.services.otp_verification import (
    OtpExpired,
    OtpInvalid,
    OtpVerificationService,
)
from app.services.registration import (
    OtpDispatchFailed,
    OtpRateLimited,
    PhoneAlreadyRegistered,
    RegistrationService,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
async def register(
    body: RegisterRequest,
    service: Annotated[RegistrationService, Depends(get_registration_service)],
) -> RegisterResponse | JSONResponse:
    try:
        result = await service.register(
            phone=body.phone,
            role=body.role,
            email=body.email,
            seller_authority_type=body.seller_authority_type,
        )
    except PhoneAlreadyRegistered:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "PHONE_ALREADY_REGISTERED",
            "A user with this phone number already exists.",
        )
    except OtpRateLimited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "OTP_RATE_LIMITED",
            "Too many OTP requests for this phone. Try again later.",
        )
    except OtpDispatchFailed:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "OTP_DISPATCH_FAILED",
            "Could not send the verification SMS. Please retry.",
        )

    return RegisterResponse(
        user_id=result.user_id,
        message=f"OTP sent to {body.phone}",
        otp_expires_in_seconds=result.otp_expires_in_seconds,
    )


@router.post("/otp/verify", response_model=OtpVerifyResponse)
async def otp_verify(
    body: OtpVerifyRequest,
    service: Annotated[OtpVerificationService, Depends(get_otp_verification_service)],
) -> OtpVerifyResponse | JSONResponse:
    try:
        result = await service.verify(phone=body.phone, code=body.otp, purpose=body.purpose)
    except OtpExpired:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "OTP_EXPIRED",
            "The OTP has expired. Request a new code.",
        )
    except OtpInvalid:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "OTP_INVALID",
            "The OTP is invalid or has already been used.",
        )

    # role comes from the DB as a free str; UserPublic narrows it to the
    # Role Literal. Construct via model_validate so Pydantic does the
    # check at runtime — an unexpected role surfaces as a 500 rather than
    # silently widening the contract.
    return OtpVerifyResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        access_expires_in=result.tokens.access_expires_in,
        user=UserPublic.model_validate(
            {"id": result.user_id, "role": result.role, "verified_status": result.verified_status}
        ),
    )
