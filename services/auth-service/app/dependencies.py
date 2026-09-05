"""FastAPI dependency wiring.

Single source of truth for the object graph: how Settings becomes a
Redis client, how a session becomes a UserRepository, how those combine
into a RegistrationService. Route handlers depend on the service-level
factories below; tests override these via app.dependency_overrides.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.bvn import BvnVerifier, build_bvn_verifier
from app.adapters.deals import DealChecker, build_deal_checker
from app.adapters.document_storage import DocumentStorage, build_document_storage
from app.adapters.email_verification import (
    EmailVerificationSender,
    build_email_verification_client,
)
from app.adapters.nin import NinVerifier, build_nin_verifier
from app.adapters.twilio import SmsClient, build_sms_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.buyer_profile_repo import BuyerProfileRepository
from app.repositories.email_verification_repo import EmailVerificationRepository
from app.repositories.otp_repo import OtpRepository
from app.repositories.realtor_registration_repo import RealtorRegistrationRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import AuthenticationError, AuthorizationError, CurrentUser, parse_bearer
from app.services.account import AccountService
from app.services.avatar_upload import AvatarService
from app.services.buyer_profile import BuyerProfileService
from app.services.bvn_verification import BvnVerificationService
from app.services.change_password import ChangePasswordService
from app.services.delete_account import DeleteAccountService
from app.services.email_verification import EmailVerificationService
from app.services.jwt_service import JwtService, TokenExpired, TokenInvalid
from app.services.login import LoginService
from app.services.logout import LogoutService
from app.services.nin_verification import NinVerificationService
from app.services.otp_attempts import OtpAttemptLimiter
from app.services.otp_resend import OtpResendService
from app.services.otp_verification import OtpVerificationService
from app.services.password_reset import (
    RESET_RATE_LIMIT_PREFIX,
    ForgotPasswordService,
    ResetPasswordService,
)
from app.services.poa_document import PoaDocumentService
from app.services.poa_notifier import PoaNotifier, build_poa_notifier
from app.services.poa_queue import PoaQueueService
from app.services.poa_review import PoaReviewService
from app.services.poa_upload import PoaUploadService
from app.services.profile import ProfileService
from app.services.rate_limit import OtpRateLimiter
from app.services.realtor_registration import RealtorRegistrationService
from app.services.registration import RegistrationService
from app.services.resend_verification import ResendVerificationService
from app.services.seller_authority import SellerAuthorityService
from app.services.seller_poa_status import SellerPoaStatusService
from app.services.set_password import SetPasswordService
from app.services.token_refresh import TokenRefreshService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_redis: Redis | None = None
_sms_client: SmsClient | None = None
_email_sender: EmailVerificationSender | None = None
_bvn_verifier: BvnVerifier | None = None
_nin_verifier: NinVerifier | None = None
_document_storage: DocumentStorage | None = None
_poa_notifier: PoaNotifier | None = None
_deal_checker: DealChecker | None = None


async def get_redis(settings: SettingsDep) -> Redis | None:
    """Lazy-build a process-wide Redis client.

    Returns None if construction fails — callers (rate limiter, cache
    helper) are designed to fail open against a None client. We don't
    ping on construction because that would add a startup hop per
    process and Redis failures should surface as fail-open at use time.
    """
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


async def get_sms_client(settings: SettingsDep) -> SmsClient:
    """Process-wide Twilio client. The factory picks fake vs real."""
    global _sms_client
    if _sms_client is None:
        _sms_client = build_sms_client(
            use_fake=settings.twilio_use_fake,
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
            base_url=settings.twilio_base_url,
            timeout_seconds=settings.twilio_timeout_seconds,
        )
    return _sms_client


async def get_email_sender(settings: SettingsDep) -> EmailVerificationSender:
    """Process-wide verification-email sender. The factory picks the in-memory
    fake (local/CI) vs the configured provider (Resend for V1)."""
    global _email_sender
    if _email_sender is None:
        _email_sender = build_email_verification_client(
            provider=settings.email_provider,
            use_fake=settings.email_verification_use_fake,
            api_key=settings.resend_api_key,
            from_address=settings.email_from_address,
            timeout_seconds=settings.email_timeout_seconds,
        )
    return _email_sender


async def get_bvn_verifier(settings: SettingsDep) -> BvnVerifier:
    """Process-wide BVN verifier. The factory picks fake vs real bureau."""
    global _bvn_verifier
    if _bvn_verifier is None:
        _bvn_verifier = build_bvn_verifier(
            use_fake=settings.bvn_use_fake,
            api_url=settings.bvn_api_url,
            api_key=settings.bvn_api_key,
            timeout_seconds=settings.bvn_timeout_seconds,
        )
    return _bvn_verifier


async def get_nin_verifier(settings: SettingsDep) -> NinVerifier:
    """Process-wide NIN verifier. The factory picks fake vs real bureau."""
    global _nin_verifier
    if _nin_verifier is None:
        _nin_verifier = build_nin_verifier(
            use_fake=settings.nin_use_fake,
            api_url=settings.nin_api_url,
            api_key=settings.nin_api_key,
            timeout_seconds=settings.nin_timeout_seconds,
        )
    return _nin_verifier


async def get_document_storage(settings: SettingsDep) -> DocumentStorage:
    """Process-wide PoA document storage. The factory picks the in-memory
    fake (local/CI) vs the real private-bucket S3 client (production)."""
    global _document_storage
    if _document_storage is None:
        _document_storage = build_document_storage(
            use_fake=settings.poa_storage_use_fake,
            bucket=settings.poa_s3_bucket,
            region=settings.poa_s3_region,
            endpoint_url=settings.poa_s3_endpoint_url,
        )
    return _document_storage


async def get_deal_checker(settings: SettingsDep) -> DealChecker:
    """Process-wide client for transaction-service's active-deal check.

    ⚠️ The fake reports "no active deals", so binding it in production would
    silently disable the deletion guard. `deal_check_use_fake` must be false
    outside local/CI.
    """
    global _deal_checker
    if _deal_checker is None:
        _deal_checker = build_deal_checker(
            use_fake=settings.deal_check_use_fake,
            base_url=settings.transaction_service_url,
        )
    return _deal_checker


RedisDep = Annotated["Redis | None", Depends(get_redis)]
SmsClientDep = Annotated[SmsClient, Depends(get_sms_client)]
EmailSenderDep = Annotated[EmailVerificationSender, Depends(get_email_sender)]
BvnVerifierDep = Annotated[BvnVerifier, Depends(get_bvn_verifier)]
NinVerifierDep = Annotated[NinVerifier, Depends(get_nin_verifier)]
DocumentStorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]
DealCheckerDep = Annotated[DealChecker, Depends(get_deal_checker)]


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def _otp_repo(session: SessionDep) -> OtpRepository:
    return OtpRepository(session)


def _email_token_repo(session: SessionDep) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


def _refresh_token_repo(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def _auth_credentials_repo(session: SessionDep) -> AuthCredentialsRepository:
    return AuthCredentialsRepository(session)


def _buyer_profile_repo(session: SessionDep) -> BuyerProfileRepository:
    return BuyerProfileRepository(session)


def _realtor_registration_repo(session: SessionDep) -> RealtorRegistrationRepository:
    return RealtorRegistrationRepository(session)


def _jwt_service(settings: SettingsDep) -> JwtService:
    return JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )


def _rate_limiter(redis: RedisDep, settings: SettingsDep) -> OtpRateLimiter:
    return OtpRateLimiter(redis, max_per_hour=settings.otp_rate_limit_per_hour)


def _reset_rate_limiter(redis: RedisDep, settings: SettingsDep) -> OtpRateLimiter:
    """Forgot-password budget. Same allowance as the OTP one but its own Redis
    namespace: it is keyed on the email, and sharing the OTP namespace would let
    a verification resend eat a user's reset allowance for that same address."""
    return OtpRateLimiter(
        redis,
        max_per_hour=settings.otp_rate_limit_per_hour,
        key_prefix=RESET_RATE_LIMIT_PREFIX,
    )


def _otp_attempts(redis: RedisDep, settings: SettingsDep) -> OtpAttemptLimiter:
    return OtpAttemptLimiter(redis, max_attempts=settings.otp_max_attempts)


def get_registration_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    email_tokens: Annotated[EmailVerificationRepository, Depends(_email_token_repo)],
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_rate_limiter)],
    sms: SmsClientDep,
    email_sender: EmailSenderDep,
    settings: SettingsDep,
) -> RegistrationService:
    # Both channels are wired unconditionally — which one runs is the caller's
    # choice per request (SCRUM-180), not a deploy-time switch.
    return RegistrationService(
        users=users,
        otps=otps,
        email_tokens=email_tokens,
        credentials=credentials,
        rate_limiter=rate_limiter,
        sms=sms,
        email_sender=email_sender,
        otp_expire_minutes=settings.otp_expire_minutes,
        email_expire_minutes=settings.email_verification_expire_minutes,
        verify_base_url=settings.email_verification_base_url,
    )


def get_email_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    email_tokens: Annotated[EmailVerificationRepository, Depends(_email_token_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> EmailVerificationService:
    return EmailVerificationService(
        users=users,
        tokens=email_tokens,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
    )


def get_resend_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    email_tokens: Annotated[EmailVerificationRepository, Depends(_email_token_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_rate_limiter)],
    email_sender: EmailSenderDep,
    settings: SettingsDep,
) -> ResendVerificationService:
    return ResendVerificationService(
        users=users,
        tokens=email_tokens,
        email_sender=email_sender,
        rate_limiter=rate_limiter,
        verification_expire_minutes=settings.email_verification_expire_minutes,
        verify_base_url=settings.email_verification_base_url,
    )


def get_forgot_password_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    email_tokens: Annotated[EmailVerificationRepository, Depends(_email_token_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_reset_rate_limiter)],
    email_sender: EmailSenderDep,
    settings: SettingsDep,
) -> ForgotPasswordService:
    return ForgotPasswordService(
        users=users,
        tokens=email_tokens,
        email_sender=email_sender,
        rate_limiter=rate_limiter,
        reset_expire_minutes=settings.password_reset_expire_minutes,
        reset_base_url=settings.password_reset_base_url,
    )


def get_reset_password_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    email_tokens: Annotated[EmailVerificationRepository, Depends(_email_token_repo)],
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
) -> ResetPasswordService:
    return ResetPasswordService(
        users=users,
        tokens=email_tokens,
        credentials=credentials,
        refresh_tokens=refresh_tokens,
    )


def get_login_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    registration_numbers: Annotated[
        RealtorRegistrationRepository, Depends(_realtor_registration_repo)
    ],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> LoginService:
    return LoginService(
        users=users,
        credentials=credentials,
        refresh_tokens=refresh_tokens,
        registration_numbers=registration_numbers,
        jwt=jwt_service,
    )


def get_set_password_service(
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
) -> SetPasswordService:
    return SetPasswordService(credentials=credentials)


def get_account_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    buyer_profiles: Annotated[BuyerProfileRepository, Depends(_buyer_profile_repo)],
    registration_numbers: Annotated[
        RealtorRegistrationRepository, Depends(_realtor_registration_repo)
    ],
) -> AccountService:
    return AccountService(
        users=users, buyer_profiles=buyer_profiles, registration_numbers=registration_numbers
    )


def get_change_password_service(
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
) -> ChangePasswordService:
    return ChangePasswordService(credentials=credentials, refresh_tokens=refresh_tokens)


def get_avatar_service(
    settings: SettingsDep,
    users: Annotated[UserRepository, Depends(_user_repo)],
    storage: DocumentStorageDep,
) -> AvatarService:
    return AvatarService(
        users=users,
        storage=storage,
        max_upload_bytes=settings.avatar_max_upload_bytes,
        url_ttl_seconds=settings.poa_presign_ttl_seconds,
    )


def get_delete_account_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    deals: DealCheckerDep,
    storage: DocumentStorageDep,
) -> DeleteAccountService:
    return DeleteAccountService(
        users=users, refresh_tokens=refresh_tokens, deals=deals, storage=storage
    )


def get_profile_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
) -> ProfileService:
    return ProfileService(users=users)


def get_seller_authority_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
) -> SellerAuthorityService:
    return SellerAuthorityService(users=users)


def get_seller_poa_status_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
) -> SellerPoaStatusService:
    return SellerPoaStatusService(users=users, audit=audit)


def get_buyer_profile_service(
    profiles: Annotated[BuyerProfileRepository, Depends(_buyer_profile_repo)],
) -> BuyerProfileService:
    return BuyerProfileService(profiles=profiles)


def get_otp_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
    attempts: Annotated[OtpAttemptLimiter, Depends(_otp_attempts)],
    settings: SettingsDep,
) -> OtpVerificationService:
    return OtpVerificationService(
        users=users,
        otps=otps,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
        attempts=attempts,
        otp_expire_minutes=settings.otp_expire_minutes,
    )


def get_token_refresh_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> TokenRefreshService:
    return TokenRefreshService(
        users=users,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
    )


def get_logout_service(
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> LogoutService:
    return LogoutService(refresh_tokens=refresh_tokens, jwt=jwt_service)


def get_bvn_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    verifier: BvnVerifierDep,
    settings: SettingsDep,
) -> BvnVerificationService:
    return BvnVerificationService(
        users=users,
        verifier=verifier,
        pepper=settings.bvn_pepper,
    )


def get_nin_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    verifier: NinVerifierDep,
    settings: SettingsDep,
) -> NinVerificationService:
    return NinVerificationService(
        users=users,
        verifier=verifier,
        pepper=settings.nin_pepper,
    )


def get_poa_upload_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    storage: DocumentStorageDep,
    settings: SettingsDep,
) -> PoaUploadService:
    return PoaUploadService(
        users=users,
        audit=audit,
        storage=storage,
        max_upload_bytes=settings.poa_max_upload_bytes,
    )


def get_poa_queue_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
) -> PoaQueueService:
    return PoaQueueService(users=users)


def get_poa_notifier(settings: SettingsDep) -> PoaNotifier:
    global _poa_notifier
    if _poa_notifier is None:
        _poa_notifier = build_poa_notifier(
            enabled=settings.notifications_enabled,
            broker_url=settings.celery_broker_url,
        )
    return _poa_notifier


def get_poa_review_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    notifier: Annotated[PoaNotifier, Depends(get_poa_notifier)],
) -> PoaReviewService:
    return PoaReviewService(users=users, audit=audit, notifier=notifier)


def get_poa_document_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    storage: DocumentStorageDep,
) -> PoaDocumentService:
    return PoaDocumentService(users=users, audit=audit, storage=storage)


async def get_current_user(
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity.

    Raises AuthenticationError (-> 401 envelope) for a missing, malformed,
    expired, or otherwise invalid access token.
    """
    token = parse_bearer(authorization)
    try:
        claims = jwt_service.decode(token, expected_type="access")
    except TokenExpired as exc:
        raise AuthenticationError("TOKEN_EXPIRED", "Access token has expired.") from exc
    except TokenInvalid as exc:
        raise AuthenticationError("TOKEN_INVALID", "Access token is invalid.") from exc

    # An access token always carries a role; guard defensively so a
    # malformed-but-signed token can't yield a None role downstream.
    if claims.role is None:
        raise AuthenticationError("TOKEN_INVALID", "Access token is missing a role.")
    return CurrentUser(user_id=claims.user_id, role=claims.role)


async def require_legal_team(
    request: Request,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    settings: SettingsDep,
) -> CurrentUser:
    """Legal-team gate: a valid legal_team JWT AND (if configured) a whitelisted
    IP. CLAUDE.md requires both for admin endpoints; Kong enforces the IP
    allowlist at the edge and this app-level check is defence in depth. Raises
    AuthorizationError -> 403."""
    if caller.role != "legal_team":
        raise AuthorizationError("LEGAL_TEAM_FORBIDDEN", "Legal-team access required.")
    allowlist = [ip.strip() for ip in settings.legal_team_ip_allowlist.split(",") if ip.strip()]
    if allowlist:
        client_ip = request.client.host if request.client else None
        if client_ip not in allowlist:
            raise AuthorizationError(
                "LEGAL_TEAM_IP_FORBIDDEN", "Your IP is not permitted for legal-team access."
            )
    return caller


async def require_admin(
    caller: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Admin gate for the /internal endpoints (SCRUM-207).

    Role only — deliberately NO IP allowlist, unlike require_legal_team above.
    These endpoints are called by a SIBLING SERVICE forwarding the admin's own
    bearer token (realtor-service, when an admin approves a realtor), so the
    request arrives from realtor-service's address and never from the admin's
    browser. An allowlist here would check the wrong machine and reject every
    legitimate call.

    What replaces it, per CLAUDE.md §4's "admin endpoints need JWT + IP
    whitelist": the /internal prefix is absent from infra/kong/kong.yml, and
    auth-service is a private service reachable only through Kong. There is no
    route from the internet to these paths at all — the network boundary does
    the job the allowlist would have done, and does it for every caller rather
    than a listed few.

    ⚠️ If /internal is ever added to kong.yml, this gate becomes the ONLY
    protection and an allowlist has to come back with it. Do not add it.
    """
    if caller.role != "admin":
        raise AuthorizationError("ADMIN_FORBIDDEN", "Admin access required.")
    return caller


def get_realtor_registration_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    numbers: Annotated[RealtorRegistrationRepository, Depends(_realtor_registration_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
) -> RealtorRegistrationService:
    return RealtorRegistrationService(users=users, numbers=numbers, audit=audit)


def get_otp_resend_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_rate_limiter)],
    sms: SmsClientDep,
    settings: SettingsDep,
) -> OtpResendService:
    return OtpResendService(
        users=users,
        otps=otps,
        sms=sms,
        rate_limiter=rate_limiter,
        otp_expire_minutes=settings.otp_expire_minutes,
    )
