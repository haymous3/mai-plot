"""Unit tests for ReauthService — "confirm your password" (SCRUM-223)."""

from __future__ import annotations

from uuid import UUID, uuid4

import jwt
import pytest

from app.repositories.user_repo import UserCore
from app.services.jwt_service import JwtService, TokenInvalid
from app.services.password import hash_password
from app.services.rate_limit import RateLimitResult
from app.services.reauth import ReauthFailed, ReauthRateLimited, ReauthService

pytestmark = pytest.mark.asyncio

_STRONG = "SecurePass123!"
_SECRET = "test-secret-please-ignore-must-be-long-enough"
_ISSUER = "maiplot-platform"


class _Users:
    """`owner` holds the password; `members` share its login (SCRUM-236)."""

    def __init__(self, owner: UUID, members: list[UUID] | None = None) -> None:
        self._owner = owner
        self._members = members or [owner]

    async def login_owner_id(self, user_id: UUID) -> UUID | None:
        return self._owner

    async def login_group(self, owner_id: UUID) -> list[UserCore]:
        return [UserCore(id=m, role="seller", verified_status="id_verified") for m in self._members]


class _Credentials:
    def __init__(self, hashes: dict[UUID, str]) -> None:
        self._hashes = hashes
        self.read_for: list[UUID] = []

    async def get_password_hash(self, user_id: UUID) -> str | None:
        self.read_for.append(user_id)
        return self._hashes.get(user_id)


class _Limiter:
    def __init__(self, *, allowed: bool = True) -> None:
        self._allowed = allowed
        self.keys: list[str] = []

    async def check_and_record(self, identifier: str) -> RateLimitResult:
        self.keys.append(identifier)
        return RateLimitResult(allowed=self._allowed, remaining=0)


def _jwt() -> JwtService:
    return JwtService(
        secret=_SECRET, issuer=_ISSUER, access_expire_minutes=15, refresh_expire_days=7
    )


def _service(
    users: _Users, credentials: _Credentials, limiter: _Limiter | None = None
) -> ReauthService:
    return ReauthService(
        users=users,  # type: ignore[arg-type]
        credentials=credentials,  # type: ignore[arg-type]
        rate_limiter=limiter or _Limiter(),  # type: ignore[arg-type]
        jwt=_jwt(),
        token_minutes=5,
    )


async def test_right_password_mints_a_short_reauth_token_for_the_caller() -> None:
    user = uuid4()
    service = _service(_Users(user), _Credentials({user: hash_password(_STRONG)}))

    result = await service.confirm(user_id=user, password=_STRONG)

    claims = jwt.decode(result.token, _SECRET, algorithms=["HS256"], issuer=_ISSUER)
    assert claims["type"] == "reauth"
    assert claims["sub"] == str(user)
    assert "role" not in claims
    assert claims["exp"] - claims["iat"] == 300
    assert result.expires_in == 300


async def test_a_seller_on_a_shared_login_confirms_with_the_owners_password() -> None:
    """The password is the LOGIN's; the token names the account asking."""
    owner, seller = uuid4(), uuid4()
    creds = _Credentials({owner: hash_password(_STRONG)})
    service = _service(_Users(owner, [owner, seller]), creds)

    result = await service.confirm(user_id=seller, password=_STRONG)

    assert creds.read_for == [owner]
    claims = jwt.decode(result.token, _SECRET, algorithms=["HS256"], issuer=_ISSUER)
    assert claims["sub"] == str(seller)


async def test_wrong_password_is_refused() -> None:
    user = uuid4()
    service = _service(_Users(user), _Credentials({user: hash_password(_STRONG)}))

    with pytest.raises(ReauthFailed):
        await service.confirm(user_id=user, password="WrongPass123!")


async def test_an_account_without_a_password_is_refused() -> None:
    user = uuid4()
    with pytest.raises(ReauthFailed):
        await _service(_Users(user), _Credentials({})).confirm(user_id=user, password=_STRONG)


async def test_attempts_are_capped_per_account_before_the_password_is_read() -> None:
    user = uuid4()
    creds = _Credentials({user: hash_password(_STRONG)})
    limiter = _Limiter(allowed=False)

    with pytest.raises(ReauthRateLimited):
        await _service(_Users(user), creds, limiter).confirm(user_id=user, password=_STRONG)
    assert limiter.keys == [str(user)]
    assert creds.read_for == []


async def test_a_reauth_token_is_not_an_access_or_refresh_token() -> None:
    user = uuid4()
    token = (
        await _service(_Users(user), _Credentials({user: hash_password(_STRONG)})).confirm(
            user_id=user, password=_STRONG
        )
    ).token

    for expected in ("access", "refresh"):
        with pytest.raises(TokenInvalid):
            _jwt().decode(token, expected_type=expected)
