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
    get_account_service,
    get_avatar_service,
    get_buyer_profile_service,
    get_bvn_verification_service,
    get_change_password_service,
    get_current_user,
    get_delete_account_service,
    get_email_verification_service,
    get_forgot_password_service,
    get_login_service,
    get_logout_service,
    get_nin_verification_service,
    get_otp_resend_service,
    get_otp_verification_service,
    get_poa_upload_service,
    get_profile_service,
    get_registration_service,
    get_resend_verification_service,
    get_reset_password_service,
    get_seller_authority_service,
    get_seller_poa_status_service,
    get_set_password_service,
    get_token_refresh_service,
)
from app.schemas.auth import (
    AccountResponse,
    AvatarResponse,
    BuyerProfileRequest,
    BuyerProfileResponse,
    BvnVerifyRequest,
    BvnVerifyResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    DeleteAccountResponse,
    EmailResendRequest,
    EmailResendResponse,
    EmailVerifyRequest,
    EmailVerifyResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    NinVerifyRequest,
    NinVerifyResponse,
    OtpResendRequest,
    OtpResendResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    PoaUploadResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
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
from app.services.account import AccountNotFound, AccountService
from app.services.avatar import InvalidAvatar
from app.services.avatar_upload import (
    AvatarService,
    AvatarStorageUnavailable,
    AvatarUserMissing,
)
from app.services.buyer_profile import BuyerProfileService, NotBuyer
from app.services.bvn import InvalidBvnError
from app.services.bvn_verification import (
    BvnAlreadyVerified,
    BvnVerificationService,
    BvnVerificationUnavailable,
)
from app.services.change_password import (
    ChangePasswordService,
    CurrentPasswordWrong,
    NoPasswordSet,
    SamePassword,
)
from app.services.delete_account import (
    AccountAlreadyGone,
    AccountHasActiveDeals,
    DeleteAccountService,
    DeleteCheckUnavailable,
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
    NinVerificationService,
    NinVerificationUnavailable,
)
from app.services.otp_resend import OtpResendService
from app.services.otp_verification import (
    OtpExpired,
    OtpInvalid,
    OtpInvalidWithAttempts,
    OtpTooManyAttempts,
    OtpVerificationService,
)
from app.services.password_reset import (
    ForgotPasswordService,
    PasswordResetRateLimited,
    ResetPasswordService,
    ResetTokenExpired,
    ResetTokenInvalid,
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
    OtpDispatchFailed,
    PhoneAlreadyRegistered,
    RegistrationService,
    VerificationEmailFailed,
    VerificationRateLimited,
)
from app.services.resend_verification import ResendVerificationService
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


def _error(
    status_code: int, code: str, message: str, details: dict[str, object] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": details or {}},
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
            full_name=body.full_name,
            verification_channel=body.verification_channel,
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
            "Too many verification requests. Try again later.",
        )
    except OtpDispatchFailed:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "OTP_DISPATCH_FAILED",
            "Could not send the verification code. Please retry.",
        )
    except VerificationEmailFailed:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "VERIFICATION_EMAIL_FAILED",
            "Could not send the verification email. Please retry.",
        )

    # `body.verification_channel` rather than `result.verification_channel`:
    # both hold the same value, but the request's is already narrowed to the
    # Literal by Pydantic. The service returns a plain str so the service layer
    # need not import API schema types; asserting they agree is the tests' job.
    channel = body.verification_channel
    sent_to = body.email if channel == "email" else body.phone
    noun = "link" if channel == "email" else "code"
    return RegisterResponse(
        user_id=result.user_id,
        message=f"Verification {noun} sent to {sent_to}",
        verification_expires_in_seconds=result.verification_expires_in_seconds,
        verification_channel=channel,
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


@router.post(
    "/verify/email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EmailResendResponse,
)
async def resend_verification_email(
    body: EmailResendRequest,
    service: Annotated[ResendVerificationService, Depends(get_resend_verification_service)],
) -> EmailResendResponse | JSONResponse:
    """Re-send the account-verification magic link (SCRUM-154). Public — the
    caller isn't verified yet. Always answers with the same generic 202 whether
    or not the address has an unverified account (no enumeration); only a rate
    limit surfaces a different status."""
    try:
        await service.resend(email=body.email)
    except VerificationRateLimited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "VERIFICATION_RATE_LIMITED",
            "Too many verification emails for this address. Try again later.",
        )
    return EmailResendResponse()


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
    except OtpTooManyAttempts:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "OTP_TOO_MANY_ATTEMPTS",
            "Too many incorrect codes. Request a new one.",
        )
    # MUST precede the OtpInvalid arm below — OtpInvalidWithAttempts subclasses
    # it, so the broader handler would swallow it and drop the counter.
    except OtpInvalidWithAttempts as exc:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "OTP_INVALID",
            "The OTP is invalid or has already been used.",
            {"attempts_remaining": exc.remaining},
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


@router.post(
    "/otp/resend",
    response_model=OtpResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def otp_resend(
    body: OtpResendRequest,
    service: Annotated[OtpResendService, Depends(get_otp_resend_service)],
) -> OtpResendResponse | JSONResponse:
    """Send a fresh registration OTP (SCRUM-176).

    Answers a generic 202 whether or not the number has an unverified
    account — a caller must not be able to probe which Nigerian numbers hold
    Maiplot accounts. Only the rate limit surfaces a different status, and it
    is checked before the lookup so even that leaks nothing.
    """
    try:
        await service.resend(phone=body.phone)
    except VerificationRateLimited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "VERIFICATION_RATE_LIMITED",
            "Too many verification codes for this number. Try again later.",
        )
    return OtpResendResponse()


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ForgotPasswordResponse,
)
async def forgot_password(
    body: ForgotPasswordRequest,
    service: Annotated[ForgotPasswordService, Depends(get_forgot_password_service)],
) -> ForgotPasswordResponse | JSONResponse:
    """Start a password reset (SCRUM-191). Public — the caller cannot log in.

    Answers with the same generic 202 whether or not the address has an
    account; only a rate limit surfaces a different status. Do not add a
    "no such account" branch here, and do not make the 202 conditional: the
    response is the enumeration surface.
    """
    try:
        await service.request(email=body.email)
    except PasswordResetRateLimited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "PASSWORD_RESET_RATE_LIMITED",
            "Too many reset requests for this address. Try again later.",
        )
    return ForgotPasswordResponse()


@router.post("/password/reset", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    service: Annotated[ResetPasswordService, Depends(get_reset_password_service)],
) -> ResetPasswordResponse | JSONResponse:
    """Finish a password reset (SCRUM-191). The frontend reads the token from
    the emailed link's query string and POSTs it here with the new password.

    Deliberately issues no tokens — the user is sent to /login. This is also
    the only way a phone-OTP-only account gets a first password without ever
    logging in, which matters while SMS to Nigerian networks is unavailable
    (CLAUDE.md §2).
    """
    try:
        await service.reset(token=body.token, new_password=body.new_password)
    except ResetTokenExpired:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "RESET_TOKEN_EXPIRED",
            "This reset link has expired. Request a new one.",
        )
    except ResetTokenInvalid:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "RESET_TOKEN_INVALID",
            "This reset link is invalid or has already been used.",
        )
    except WeakPassword:
        return _error(
            422,
            "PASSWORD_TOO_WEAK",
            "Password must be at least 8 characters and include an uppercase letter and a number.",
        )
    return ResetPasswordResponse(
        message="Password reset. Please sign in with your new password.",
        sessions_revoked=True,
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


@router.get("/me", response_model=AccountResponse)
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AccountService, Depends(get_account_service)],
    avatars: Annotated[AvatarService, Depends(get_avatar_service)],
) -> AccountResponse | JSONResponse:
    """The caller's own account, for pre-filling Settings (SCRUM-188).

    404 rather than 200-with-nulls when the account is gone (soft-deleted or
    deactivated): a token can outlive the account it was issued for, and a
    half-populated body would read as "you have no name" rather than "this
    account no longer exists".
    """
    try:
        account = await service.get(current_user.user_id)
    except AccountNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "ACCOUNT_NOT_FOUND", "Account not found.")
    # role comes from the DB as a free str; AccountResponse narrows it to the
    # AccountRole Literal. model_validate so Pydantic checks at runtime — an
    # unexpected role surfaces as a 500 rather than silently widening the
    # contract. Same idiom as UserPublic on the verify routes.
    return AccountResponse.model_validate(
        {
            "id": account.id,
            "role": account.role,
            "verified_status": account.verified_status,
            "email": account.email,
            "phone": account.phone,
            "full_name": account.full_name,
            "seller_authority_type": account.seller_authority_type,
            "poa_verified_status": account.poa_verified_status,
            "bvn_verified": account.bvn_verified,
            "nin_verified": account.nin_verified,
            # Minted here, not in AccountService: turning a key into a URL is
            # a storage concern, and it keeps the account read free of any
            # S3 dependency.
            "avatar_url": avatars.presigned_url(account.avatar_s3_key),
            "employment_status": account.employment_status,
            "preferred_location": account.preferred_location,
            "budget_kobo": account.budget_kobo,
        }
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ChangePasswordService, Depends(get_change_password_service)],
) -> ChangePasswordResponse | JSONResponse:
    """Change the password, proving knowledge of the current one (SCRUM-188).

    Distinct from /auth/set-password, which takes no current password: that one
    is the post-verification path where the freshly issued token IS the proof.
    A Settings form must not accept a session alone as authority to rotate the
    password.

    Every refresh token is revoked on success, so the user is signed out
    everywhere and must sign in again with the new password.
    """
    try:
        await service.change(
            user_id=current_user.user_id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except NoPasswordSet:
        return _error(
            status.HTTP_409_CONFLICT,
            "NO_PASSWORD_SET",
            "This account has no password yet. Set one instead of changing it.",
        )
    except CurrentPasswordWrong:
        # Deliberately the same shape as a login failure and never says which
        # of the two passwords was at fault.
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "CURRENT_PASSWORD_INCORRECT",
            "Your current password is incorrect.",
        )
    except SamePassword:
        return _error(
            422,
            "PASSWORD_UNCHANGED",
            "Your new password must be different from your current one.",
        )
    except WeakPassword:
        return _error(
            422,
            "PASSWORD_TOO_WEAK",
            "Password must be at least 8 characters and include an uppercase letter and a number.",
        )
    return ChangePasswordResponse(
        message="Password changed. Please sign in again.", sessions_revoked=True
    )


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


@router.post("/avatar", response_model=AvatarResponse)
async def upload_avatar(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AvatarService, Depends(get_avatar_service)],
    file: Annotated[UploadFile, File(description="Profile photo — JPEG, PNG or WebP")],
) -> AvatarResponse | JSONResponse:
    """Set the caller's profile photo (SCRUM-188).

    Open to every role. The bytes are validated server-side by magic number —
    the client-supplied filename and Content-Type are not trusted — and stored
    in the PRIVATE bucket, so the response carries a pre-signed URL rather than
    anything durable.
    """
    data = await file.read()
    try:
        result = await service.upload(user_id=current_user.user_id, data=data)
    except InvalidAvatar as exc:
        # Never echo the image bytes. Literal 422 sidesteps the
        # status.HTTP_422_* deprecation rename (see main.py).
        return _error(422, exc.code, str(exc))
    except AvatarUserMissing:
        return _error(status.HTTP_404_NOT_FOUND, "ACCOUNT_NOT_FOUND", "Account not found.")
    except AvatarStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "AVATAR_STORAGE_UNAVAILABLE",
            "Photo storage is temporarily unavailable. Please retry.",
        )
    return AvatarResponse(avatar_url=result.url)


@router.delete("/avatar", response_model=AvatarResponse)
async def delete_avatar(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AvatarService, Depends(get_avatar_service)],
) -> AvatarResponse:
    """Remove the caller's profile photo.

    Idempotent — removing a photo that is not set is success, not a 404. The
    caller asked to end up with no photo, and they already have.
    """
    await service.remove(user_id=current_user.user_id)
    return AvatarResponse(avatar_url=None)


@router.post("/account/delete", response_model=DeleteAccountResponse)
async def delete_account(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[DeleteAccountService, Depends(get_delete_account_service)],
) -> DeleteAccountResponse | JSONResponse:
    """Soft-delete the caller's own account (SCRUM-188).

    POST, not DELETE, because it is guarded and consequential rather than a
    plain resource removal — and because the guard can legitimately refuse.

    Soft: transactions, escrow and audit rows survive for CBN/AMLON. Migrations
    0009/0010 make the deletion release the phone and email for reuse.

    ⚠️ 503 when the active-deal guard cannot be evaluated. That is deliberate
    fail-CLOSED behaviour — see adapters/deals.py. A retry in a minute costs
    the user little; deleting an account over an unchecked escrow balance is
    not recoverable through the product.
    """
    # The caller's own token is forwarded to transaction-service, whose
    # active-deal endpoint is caller-scoped. Nothing else needs to be trusted.
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""

    try:
        await service.delete(user_id=current_user.user_id, bearer_token=token)
    except AccountHasActiveDeals:
        return _error(
            status.HTTP_409_CONFLICT,
            "ACCOUNT_HAS_ACTIVE_DEALS",
            "You still have a deal in progress. Complete or cancel it before "
            "deleting your account.",
        )
    except DeleteCheckUnavailable:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DELETE_UNAVAILABLE",
            "We could not confirm your account has no deals in progress. Please try again shortly.",
        )
    except AccountAlreadyGone:
        return _error(status.HTTP_404_NOT_FOUND, "ACCOUNT_NOT_FOUND", "Account not found.")

    return DeleteAccountResponse(message="Your account has been deleted.", sessions_revoked=True)
