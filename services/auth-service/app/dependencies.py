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
from app.adapters.document_storage import DocumentStorage, build_document_storage
from app.adapters.nin import NinVerifier, build_nin_verifier
from app.adapters.termii import TermiiClient, build_termii_client
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.buyer_profile_repo import BuyerProfileRepository
from app.repositories.otp_repo import OtpRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.security import AuthenticationError, AuthorizationError, CurrentUser, parse_bearer
from app.services.buyer_profile import BuyerProfileService
from app.services.bvn_verification import BvnVerificationService
from app.services.jwt_service import JwtService, TokenExpired, TokenInvalid
from app.services.login import LoginService
from app.services.logout import LogoutService
from app.services.nin_verification import NinVerificationService
from app.services.otp_verification import OtpVerificationService
from app.services.poa_document import PoaDocumentService
from app.services.poa_notifier import PoaNotifier, build_poa_notifier
from app.services.poa_queue import PoaQueueService
from app.services.poa_review import PoaReviewService
from app.services.poa_upload import PoaUploadService
from app.services.profile import ProfileService
from app.services.rate_limit import OtpRateLimiter
from app.services.registration import RegistrationService
from app.services.seller_authority import SellerAuthorityService
from app.services.set_password import SetPasswordService
from app.services.token_refresh import TokenRefreshService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_redis: Redis | None = None
_termii: TermiiClient | None = None
_bvn_verifier: BvnVerifier | None = None
_nin_verifier: NinVerifier | None = None
_document_storage: DocumentStorage | None = None
_poa_notifier: PoaNotifier | None = None


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


async def get_termii(settings: SettingsDep) -> TermiiClient:
    """Process-wide Termii client. The factory picks fake vs real."""
    global _termii
    if _termii is None:
        _termii = build_termii_client(
            use_fake=settings.termii_use_fake,
            api_key=settings.termii_api_key,
            sender_id=settings.termii_sender_id,
            base_url=settings.termii_base_url,
            timeout_seconds=settings.termii_timeout_seconds,
        )
    return _termii


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


RedisDep = Annotated["Redis | None", Depends(get_redis)]
TermiiDep = Annotated[TermiiClient, Depends(get_termii)]
BvnVerifierDep = Annotated[BvnVerifier, Depends(get_bvn_verifier)]
NinVerifierDep = Annotated[NinVerifier, Depends(get_nin_verifier)]
DocumentStorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]


def _user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def _otp_repo(session: SessionDep) -> OtpRepository:
    return OtpRepository(session)


def _refresh_token_repo(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def _auth_credentials_repo(session: SessionDep) -> AuthCredentialsRepository:
    return AuthCredentialsRepository(session)


def _buyer_profile_repo(session: SessionDep) -> BuyerProfileRepository:
    return BuyerProfileRepository(session)


def _jwt_service(settings: SettingsDep) -> JwtService:
    return JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )


def _rate_limiter(redis: RedisDep, settings: SettingsDep) -> OtpRateLimiter:
    return OtpRateLimiter(redis, max_per_hour=settings.otp_rate_limit_per_hour)


def get_registration_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    rate_limiter: Annotated[OtpRateLimiter, Depends(_rate_limiter)],
    termii: TermiiDep,
    settings: SettingsDep,
) -> RegistrationService:
    return RegistrationService(
        users=users,
        otps=otps,
        credentials=credentials,
        rate_limiter=rate_limiter,
        termii=termii,
        otp_expire_minutes=settings.otp_expire_minutes,
    )


def get_login_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> LoginService:
    return LoginService(
        users=users,
        credentials=credentials,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
    )


def get_set_password_service(
    credentials: Annotated[AuthCredentialsRepository, Depends(_auth_credentials_repo)],
) -> SetPasswordService:
    return SetPasswordService(credentials=credentials)


def get_profile_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
) -> ProfileService:
    return ProfileService(users=users)


def get_seller_authority_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
) -> SellerAuthorityService:
    return SellerAuthorityService(users=users)


def get_buyer_profile_service(
    profiles: Annotated[BuyerProfileRepository, Depends(_buyer_profile_repo)],
) -> BuyerProfileService:
    return BuyerProfileService(profiles=profiles)


def get_otp_verification_service(
    users: Annotated[UserRepository, Depends(_user_repo)],
    otps: Annotated[OtpRepository, Depends(_otp_repo)],
    refresh_tokens: Annotated[RefreshTokenRepository, Depends(_refresh_token_repo)],
    jwt_service: Annotated[JwtService, Depends(_jwt_service)],
) -> OtpVerificationService:
    return OtpVerificationService(
        users=users,
        otps=otps,
        refresh_tokens=refresh_tokens,
        jwt=jwt_service,
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
