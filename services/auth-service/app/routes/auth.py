"""/auth route handlers.

Handlers are thin: build a Pydantic request, call the service, translate
domain errors to HTTP responses matching api-contracts.md. No DB calls
here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_buyer_profile_service,
    get_bvn_verification_service,
    get_current_user,
    get_email_verification_service,
    get_login_service,
    get_logout_service,
    get_nin_verification_service,
    get_otp_verification_service,
    get_poa_upload_service,
    get_profile_service,
    get_registration_service,
    get_seller_authority_service,
    get_seller_poa_status_service,
    get_set_password_service,
    get_token_refresh_service,
)
from app.schemas.auth import (
    BuyerProfileRequest,
    BuyerProfileResponse,
    BvnVerifyRequest,
    BvnVerifyResponse,
    EmailVerifyRequest,
    EmailVerifyResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    NinVerifyRequest,
    NinVerifyResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    PoaUploadResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    RegisterRequest,
    RegisterResponse,
    SellerAuthorityRequest,
    SellerAuthorityResponse,
    SellerPoaStatusResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserPublic,
)
from app.security import CurrentUser
from app.services.buyer_profile import BuyerProfileService, NotBuyer
from app.services.bvn import InvalidBvnError
from app.services.bvn_verification import (
    BvnAlreadyVerified,
    BvnVerificationService,
    BvnVerificationUnavailable,
)
from app.services.email_verification import (
    EmailTokenExpired,
    EmailTokenInvalid,
    EmailVerificationService,
)
from app.services.login import InvalidCredentials, LoginService
from app.services.logout import LogoutService
from app.services.nin import InvalidNinError
from app.services.nin_verification import (
    NinAlreadyVerified,
    NinNotEligible,
    NinVerificationService,
    NinVerificationUnavailable,
)
from app.services.otp_verification import (
    OtpExpired,
    OtpInvalid,
    OtpVerificationService,
)
from app.services.poa import InvalidPoaDocument
from app.services.poa_upload import (
    PoaAlreadySubmitted,
    PoaNotEligible,
    PoaStorageUnavailable,
    PoaUploadService,
)
from app.services.profile import EmailAlreadyInUse, InvalidFullName, ProfileService
from app.services.registration import (
    EmailAlreadyRegistered,
    PhoneAlreadyRegistered,
    RegistrationService,
    VerificationEmailFailed,
    VerificationRateLimited,
)
from app.services.seller_authority import NotSeller, SellerAuthorityService
from app.services.seller_poa_status import NotSeller as PoaNotSeller
from app.services.seller_poa_status import SellerNotFound, SellerPoaStatusService
from app.services.set_password import SetPasswordService, WeakPassword
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
    except EmailAlreadyRegistered:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "EMAIL_ALREADY_REGISTERED",
            "A user with this email address already exists.",
        )
    except PhoneAlreadyRegistered:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "PHONE_ALREADY_REGISTERED",
            "A user with this phone number already exists.",
        )
    except VerificationRateLimited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "VERIFICATION_RATE_LIMITED",
            "Too many verification emails for this address. Try again later.",
        )
    except VerificationEmailFailed:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "VERIFICATION_EMAIL_FAILED",
            "Could not send the verification email. Please retry.",
        )

    return RegisterResponse(
        user_id=result.user_id,
        message=f"Verification email sent to {body.email}",
        verification_expires_in_seconds=result.verification_expires_in_seconds,
    )


@router.post("/verify/email", response_model=EmailVerifyResponse)
async def verify_email(
    body: EmailVerifyRequest,
    service: Annotated[EmailVerificationService, Depends(get_email_verification_service)],
) -> EmailVerifyResponse | JSONResponse:
    """Confirm an account from the emailed magic link (SCRUM-152). The frontend
    landing page reads the token from the link's query string and POSTs it here;
    on success the account is marked email_verified and a JWT pair is issued
    (same shape as /auth/otp/verify)."""
    try:
        result = await service.verify(token=body.token, purpose=body.purpose)
    except EmailTokenExpired:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "EMAIL_TOKEN_EXPIRED",
            "The verification link has expired. Request a new one.",
        )
    except EmailTokenInvalid:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "EMAIL_TOKEN_INVALID",
            "The verification link is invalid or has already been used.",
        )

    return EmailVerifyResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        access_expires_in=result.tokens.access_expires_in,
        user=UserPublic.model_validate(
            {"id": result.user_id, "role": result.role, "verified_status": result.verified_status}
        ),
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
    # AccountRole Literal. Construct via model_validate so Pydantic does the
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


@router.post("/set-password", response_model=SetPasswordResponse)
async def set_password(
    body: SetPasswordRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SetPasswordService, Depends(get_set_password_service)],
) -> SetPasswordResponse | JSONResponse:
    """Set the caller's password after phone-OTP verification (SCRUM-94). Authed
    by the access token issued at /auth/otp/verify."""
    try:
        await service.set(user_id=current_user.user_id, password=body.password)
    except WeakPassword:
        return _error(
            422,
            "PASSWORD_TOO_WEAK",
            "Password must be at least 8 characters and include an uppercase letter and a number.",
        )
    return SetPasswordResponse(message="Password set")


@router.post("/profile", response_model=ProfileUpdateResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileUpdateResponse | JSONResponse:
    """Save the caller's personal details (full name + optional email) from the
    onboarding "Personal details" screen (SCRUM-132). Authed by the access token
    issued at /auth/otp/verify."""
    try:
        await service.update(
            user_id=current_user.user_id, full_name=body.full_name, email=body.email
        )
    except InvalidFullName:
        return _error(422, "FULL_NAME_REQUIRED", "Please enter your full name.")
    except EmailAlreadyInUse:
        return _error(
            409, "EMAIL_ALREADY_IN_USE", "That email is already linked to another account."
        )
    return ProfileUpdateResponse(message="Profile updated")


@router.post("/seller/authority", response_model=SellerAuthorityResponse)
async def declare_seller_authority(
    body: SellerAuthorityRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerAuthorityService, Depends(get_seller_authority_service)],
) -> SellerAuthorityResponse | JSONResponse:
    """Declare the caller's selling authority on the "Seller Verification" screen
    (SCRUM-132). A power_of_attorney declaration enters the PoA review queue and
    gates the subsequent PoA-document upload; an owner may then verify a NIN.
    Authed by the access token issued at /auth/otp/verify."""
    try:
        await service.set(
            user_id=current_user.user_id,
            role=current_user.role,
            authority_type=body.authority_type,
        )
    except NotSeller:
        return _error(403, "SELLER_ROLE_REQUIRED", "Only sellers can declare a selling authority.")
    return SellerAuthorityResponse(message="Authority declared", authority_type=body.authority_type)


@router.get("/seller/poa-status", response_model=None)
async def seller_poa_status(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[SellerPoaStatusService, Depends(get_seller_poa_status_service)],
) -> SellerPoaStatusResponse | JSONResponse:
    """The caller's own PoA verification status (SCRUM-137) — authority type,
    pending/verified/rejected status, rejection reason, and whether they may yet
    publish. Powers the seller dashboard's PoA tracking card. Seller-scoped."""
    try:
        result = await service.get(user_id=current_user.user_id, role=current_user.role)
    except PoaNotSeller:
        return _error(403, "SELLER_ROLE_REQUIRED", "Only sellers have a PoA status.")
    except SellerNotFound:
        return _error(404, "SELLER_NOT_FOUND", "No seller account found.")
    return SellerPoaStatusResponse(
        authority_type=result.authority_type,
        status=result.status,
        has_document=result.has_document,
        submitted_at=result.submitted_at,
        rejection_reason=result.rejection_reason,
        can_publish=result.can_publish,
    )


@router.post("/buyer/profile", response_model=BuyerProfileResponse)
async def save_buyer_profile(
    body: BuyerProfileRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BuyerProfileService, Depends(get_buyer_profile_service)],
) -> BuyerProfileResponse | JSONResponse:
    """Save the caller's optional buying-capacity details from the buyer
    onboarding "Personal Information" screen (SCRUM-132). Authed by the access
    token issued at /auth/otp/verify. All fields optional ("Skip for now")."""
    try:
        await service.save(
            user_id=current_user.user_id,
            role=current_user.role,
            employment_status=body.employment_status,
            preferred_location=body.preferred_location,
            budget_kobo=body.budget_kobo,
        )
    except NotBuyer:
        return _error(403, "BUYER_ROLE_REQUIRED", "Only buyers have a buyer profile.")
    return BuyerProfileResponse(message="Profile saved")


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


@router.post("/verify/bvn", status_code=status.HTTP_202_ACCEPTED, response_model=BvnVerifyResponse)
async def verify_bvn(
    body: BvnVerifyRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BvnVerificationService, Depends(get_bvn_verification_service)],
) -> BvnVerifyResponse | JSONResponse:
    try:
        result = await service.verify(user_id=current_user.user_id, bvn=body.bvn)
    except InvalidBvnError:
        # Never echo the BVN value in the error. Literal 422 sidesteps the
        # status.HTTP_422_* deprecation rename (see main.py).
        return _error(
            422,
            "BVN_FORMAT_INVALID",
            "BVN must be exactly 11 digits.",
        )
    except BvnAlreadyVerified:
        return _error(
            status.HTTP_409_CONFLICT,
            "BVN_ALREADY_VERIFIED",
            "This BVN has already been verified.",
        )
    except BvnVerificationUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "BVN_VERIFICATION_UNAVAILABLE",
            "BVN verification is temporarily unavailable. Please retry.",
        )

    return BvnVerifyResponse(message="BVN verification initiated", status=result.status)


@router.post("/verify/nin", status_code=status.HTTP_202_ACCEPTED, response_model=NinVerifyResponse)
async def verify_nin(
    body: NinVerifyRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[NinVerificationService, Depends(get_nin_verification_service)],
) -> NinVerifyResponse | JSONResponse:
    try:
        result = await service.verify(user_id=current_user.user_id, nin=body.nin)
    except NinNotEligible:
        # Only sellers with authority_type=owner may verify a NIN.
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NIN_NOT_ELIGIBLE",
            "NIN verification is only available to property owners (seller, owner authority).",
        )
    except InvalidNinError:
        # Never echo the NIN value in the error. Literal 422 sidesteps the
        # status.HTTP_422_* deprecation rename (see main.py).
        return _error(
            422,
            "NIN_FORMAT_INVALID",
            "NIN must be exactly 11 digits.",
        )
    except NinAlreadyVerified:
        return _error(
            status.HTTP_409_CONFLICT,
            "NIN_ALREADY_VERIFIED",
            "This NIN has already been verified.",
        )
    except NinVerificationUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "NIN_VERIFICATION_UNAVAILABLE",
            "NIN verification is temporarily unavailable. Please retry.",
        )

    return NinVerifyResponse(message="NIN verification initiated", status=result.status)


@router.post("/poa/upload", status_code=status.HTTP_201_CREATED, response_model=PoaUploadResponse)
async def upload_poa(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[PoaUploadService, Depends(get_poa_upload_service)],
    file: Annotated[UploadFile, File(description="PoA document — PDF or JPEG")],
) -> PoaUploadResponse | JSONResponse:
    # Read the bytes once; the service validates size + magic-number type
    # server-side (the client-supplied content type/filename is not trusted).
    data = await file.read()
    client_ip = request.client.host if request.client else None
    try:
        result = await service.upload(
            user_id=current_user.user_id,
            data=data,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except PoaNotEligible:
        # Only sellers with authority_type=power_of_attorney may upload a PoA.
        return _error(
            status.HTTP_403_FORBIDDEN,
            "POA_NOT_ELIGIBLE",
            "PoA upload is only available to sellers with power-of-attorney authority.",
        )
    except InvalidPoaDocument as exc:
        # Never echo the document bytes. Literal 422 sidesteps the
        # status.HTTP_422_* deprecation rename (see main.py).
        return _error(422, exc.code, str(exc))
    except PoaAlreadySubmitted:
        return _error(
            status.HTTP_409_CONFLICT,
            "POA_ALREADY_SUBMITTED",
            "A PoA document is already pending review or verified.",
        )
    except PoaStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "POA_STORAGE_UNAVAILABLE",
            "Document storage is temporarily unavailable. Please retry.",
        )

    return PoaUploadResponse(poa_verified_status=result.status, s3_key=result.s3_key)
