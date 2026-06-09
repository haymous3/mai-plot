"""/auth route handlers.

Handlers are thin: build a Pydantic request, call the service, translate
domain errors to HTTP responses matching api-contracts.md. No DB calls
here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_current_user,
    get_login_service,
    get_logout_service,
    get_otp_verification_service,
    get_registration_service,
    get_token_refresh_service,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    RegisterRequest,
    RegisterResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserPublic,
)
from app.security import CurrentUser
from app.services.login import InvalidCredentials, LoginService
from app.services.logout import LogoutService
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
from app.services.token_refresh import (
    RefreshTokenExpired,
    RefreshTokenInvalid,
    RefreshTokenRevoked,
    TokenRefreshService,
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
            password=body.password,
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


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    service: Annotated[LoginService, Depends(get_login_service)],
) -> LoginResponse | JSONResponse:
    try:
        result = await service.login(email=body.email, password=body.password)
    except InvalidCredentials:
        # One generic message for unknown email / no password / wrong
        # password — never reveal which, to prevent account enumeration.
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Email or password is incorrect.",
        )

    return LoginResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        access_expires_in=result.tokens.access_expires_in,
        user=UserPublic.model_validate(
            {"id": result.user_id, "role": result.role, "verified_status": result.verified_status}
        ),
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


@router.post("/token/refresh", response_model=TokenRefreshResponse)
async def token_refresh(
    body: TokenRefreshRequest,
    service: Annotated[TokenRefreshService, Depends(get_token_refresh_service)],
) -> TokenRefreshResponse | JSONResponse:
    try:
        result = await service.refresh(refresh_token=body.refresh_token)
    except RefreshTokenExpired:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "REFRESH_TOKEN_EXPIRED",
            "The refresh token has expired. Please log in again.",
        )
    except RefreshTokenRevoked:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "REFRESH_TOKEN_REVOKED",
            "The refresh token has been revoked. Please log in again.",
        )
    except RefreshTokenInvalid:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "REFRESH_TOKEN_INVALID",
            "The refresh token is invalid.",
        )

    return TokenRefreshResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        access_expires_in=result.tokens.access_expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    body: LogoutRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[LogoutService, Depends(get_logout_service)],
) -> LogoutResponse:
    await service.logout(user_id=current_user.user_id, refresh_token=body.refresh_token)
    return LogoutResponse()
