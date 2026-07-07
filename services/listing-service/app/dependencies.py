"""FastAPI dependency wiring for listing-service.

Route handlers depend on the factories here; tests override them via
app.dependency_overrides. Mirrors auth-service's dependency module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.media_storage import MediaStorage, build_media_storage
from app.adapters.search_index import SearchIndex, build_search_index
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.interest_repo import InterestRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.saved_repo import SavedListingRepository
from app.repositories.seller_repo import SellerRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.admin_queue import AdminQueueService
from app.services.express_interest import ExpressInterestService
from app.services.index_dispatch import IndexDispatcher, build_index_dispatcher
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.listing_create import ListingCreateService
from app.services.listing_detail import ListingDetailService
from app.services.listing_query import ListingQueryService
from app.services.listing_review import ListingReviewService
from app.services.listing_search import ListingSearchService
from app.services.listing_update import ListingUpdateService
from app.services.media_upload import MediaUploadService
from app.services.saved_listings import SavedListingService
from app.services.view_count_dispatch import ViewCountDispatcher, build_view_count_dispatcher

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_redis: Redis | None = None
_media_storage: MediaStorage | None = None
_search_index: SearchIndex | None = None


async def get_search_index(settings: SettingsDep) -> SearchIndex:
    """Process-wide search index. The factory picks the in-memory fake
    (local/CI) vs the real Elasticsearch client (production)."""
    global _search_index
    if _search_index is None:
        _search_index = build_search_index(
            use_fake=settings.search_use_fake,
            url=settings.elasticsearch_url,
            index=settings.es_listings_index,
            urgency_boost_weight=settings.search_urgency_boost_weight,
            urgency_scale_days=settings.search_urgency_scale_days,
        )
    return _search_index


SearchIndexDep = Annotated[SearchIndex, Depends(get_search_index)]


async def get_media_storage(settings: SettingsDep) -> MediaStorage:
    """Process-wide media storage. The factory picks the in-memory fake
    (local/CI) vs the real public-bucket S3 client (production)."""
    global _media_storage
    if _media_storage is None:
        _media_storage = build_media_storage(
            use_fake=settings.media_storage_use_fake,
            bucket=settings.media_s3_bucket,
            region=settings.media_s3_region,
            cdn_domain=settings.cloudfront_domain,
            endpoint_url=settings.media_s3_endpoint_url,
        )
    return _media_storage


MediaStorageDep = Annotated[MediaStorage, Depends(get_media_storage)]


async def get_redis(settings: SettingsDep) -> Redis | None:
    """Lazy process-wide Redis client. Returns None if construction fails —
    the cache helper fails open against a None client, so the feed/detail
    paths still serve from Postgres."""
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


RedisDep = Annotated["Redis | None", Depends(get_redis)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _seller_repo(session: SessionDep) -> SellerRepository:
    return SellerRepository(session)


def _listing_repo(session: SessionDep) -> ListingRepository:
    return ListingRepository(session)


def _audit_repo(session: SessionDep) -> AuditLogRepository:
    return AuditLogRepository(session)


def _saved_repo(session: SessionDep) -> SavedListingRepository:
    return SavedListingRepository(session)


def get_saved_listing_service(
    saved: Annotated[SavedListingRepository, Depends(_saved_repo)],
) -> SavedListingService:
    return SavedListingService(saved=saved)


def _interest_repo(session: SessionDep) -> InterestRepository:
    return InterestRepository(session)


def get_express_interest_service(
    interests: Annotated[InterestRepository, Depends(_interest_repo)],
) -> ExpressInterestService:
    return ExpressInterestService(interests=interests)


def _index_dispatcher(
    index: SearchIndexDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    settings: SettingsDep,
) -> IndexDispatcher:
    """Dispatch index syncs to Celery in prod (index_via_celery), inline in
    dev/CI. The inline transport reuses this request's session + fake index."""
    return build_index_dispatcher(
        via_celery=settings.index_via_celery, index=index, listings=listings
    )


def get_listing_create_service(
    sellers: Annotated[SellerRepository, Depends(_seller_repo)],
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    dispatch: Annotated[IndexDispatcher, Depends(_index_dispatcher)],
) -> ListingCreateService:
    return ListingCreateService(sellers=sellers, listings=listings, dispatch=dispatch)


def get_listing_search_service(index: SearchIndexDep) -> ListingSearchService:
    return ListingSearchService(index=index)


def get_admin_queue_service(
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
) -> AdminQueueService:
    return AdminQueueService(listings=listings)


def get_listing_review_service(
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    audit: Annotated[AuditLogRepository, Depends(_audit_repo)],
    dispatch: Annotated[IndexDispatcher, Depends(_index_dispatcher)],
) -> ListingReviewService:
    return ListingReviewService(listings=listings, audit=audit, dispatch=dispatch)


def get_listing_query_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    settings: SettingsDep,
) -> ListingQueryService:
    return ListingQueryService(
        redis=redis, listings=listings, ttl_seconds=settings.feed_cache_ttl_seconds
    )


def _view_count_dispatcher(
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    settings: SettingsDep,
) -> ViewCountDispatcher:
    """Dispatch view_count bumps to Celery in prod (view_count_via_celery),
    inline in dev/CI. The inline transport reuses this request's repo."""
    return build_view_count_dispatcher(via_celery=settings.view_count_via_celery, listings=listings)


def get_listing_detail_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    sellers: Annotated[SellerRepository, Depends(_seller_repo)],
    view_counter: Annotated[ViewCountDispatcher, Depends(_view_count_dispatcher)],
    settings: SettingsDep,
) -> ListingDetailService:
    return ListingDetailService(
        redis=redis,
        listings=listings,
        sellers=sellers,
        ttl_seconds=settings.listing_cache_ttl_seconds,
        view_counter=view_counter,
    )


def get_listing_update_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    dispatch: Annotated[IndexDispatcher, Depends(_index_dispatcher)],
) -> ListingUpdateService:
    return ListingUpdateService(redis=redis, listings=listings, dispatch=dispatch)


def get_media_upload_service(
    redis: RedisDep,
    listings: Annotated[ListingRepository, Depends(_listing_repo)],
    storage: MediaStorageDep,
    settings: SettingsDep,
) -> MediaUploadService:
    return MediaUploadService(
        redis=redis,
        listings=listings,
        storage=storage,
        max_photo_bytes=settings.max_photo_bytes,
        max_video_bytes=settings.max_video_bytes,
        max_photos=settings.max_photos_per_listing,
        max_videos=settings.max_videos_per_listing,
    )


async def get_current_user(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity.

    Raises AuthenticationError (-> 401 envelope) for a missing, malformed,
    expired, or otherwise invalid access token.
    """
    token = parse_bearer(authorization)
    try:
        claims = verifier.decode_access(token)
    except TokenExpired as exc:
        raise AuthenticationError("TOKEN_EXPIRED", "Access token has expired.") from exc
    except TokenInvalid as exc:
        raise AuthenticationError("TOKEN_INVALID", "Access token is invalid.") from exc

    if claims.role is None:
        raise AuthenticationError("TOKEN_INVALID", "Access token is missing a role.")
    return CurrentUser(user_id=claims.user_id, role=claims.role)


async def get_current_user_optional(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """Like get_current_user but never raises — for Auth:Optional endpoints
    (feed, detail). A missing/invalid/expired token yields None (anonymous),
    so an authenticated buyer gets the loan-eligibility indicator while
    everyone else still gets the listing."""
    if not authorization:
        return None
    try:
        claims = verifier.decode_access(parse_bearer(authorization))
    except (AuthenticationError, TokenExpired, TokenInvalid):
        return None
    if claims.role is None:
        return None
    return CurrentUser(user_id=claims.user_id, role=claims.role)


async def require_admin(
    request: Request,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    settings: SettingsDep,
) -> CurrentUser:
    """Admin gate: a valid admin JWT AND (if configured) a whitelisted IP.
    CLAUDE.md requires both; Kong enforces the IP allowlist at the edge and
    this app-level check is defence in depth. Raises AdminAccessError -> 403."""
    if caller.role != "admin":
        raise AdminAccessError("ADMIN_FORBIDDEN", "Admin access required.")
    allowlist = [ip.strip() for ip in settings.admin_ip_allowlist.split(",") if ip.strip()]
    if allowlist:
        client_ip = request.client.host if request.client else None
        if client_ip not in allowlist:
            raise AdminAccessError(
                "ADMIN_IP_FORBIDDEN", "Your IP is not permitted for admin access."
            )
    return caller
