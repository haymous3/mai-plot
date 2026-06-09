"""TokenRefreshService rotation logic with stub repos + a real JwtService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.refresh_token_repo import StoredRefreshToken
from app.repositories.user_repo import UserCore
from app.services.jwt_service import JwtService
from app.services.token_refresh import (
    RefreshTokenExpired,
    RefreshTokenInvalid,
    RefreshTokenRevoked,
    TokenRefreshService,
)

SECRET = "test-secret-please-ignore-must-be-long-enough"
ISSUER = "maiplot-platform"


def _jwt() -> JwtService:
    return JwtService(secret=SECRET, issuer=ISSUER, access_expire_minutes=15, refresh_expire_days=7)


class _StubUserRepo:
    def __init__(self, user: UserCore | None) -> None:
        self._user = user

    async def get_active_by_id(self, user_id: UUID) -> UserCore | None:
        return self._user


class _StubRefreshRepo:
    def __init__(self, stored: StoredRefreshToken | None) -> None:
        self._stored = stored
        self.revoked: list[UUID] = []
        self.created: list[dict[str, object]] = []

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        return self._stored

    async def revoke(self, token_id: UUID) -> None:
        self.revoked.append(token_id)

    async def create(self, *, user_id: UUID, token_hash: str, expires_at: datetime) -> UUID:
        new_id = uuid4()
        self.created.append({"user_id": user_id, "token_hash": token_hash, "id": new_id})
        return new_id


def _service(user_repo: _StubUserRepo, refresh_repo: _StubRefreshRepo) -> TokenRefreshService:
    return TokenRefreshService(
        users=user_repo,  # type: ignore[arg-type]
        refresh_tokens=refresh_repo,  # type: ignore[arg-type]
        jwt=_jwt(),
    )


def _stored(user_id: UUID, *, revoked: bool = False, expired: bool = False) -> StoredRefreshToken:
    now = datetime.now(UTC)
    return StoredRefreshToken(
        id=uuid4(),
        user_id=user_id,
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=7),
        revoked_at=now if revoked else None,
    )


@pytest.mark.asyncio
async def test_happy_rotation_revokes_old_and_creates_new() -> None:
    user_id = uuid4()
    tokens = _jwt().issue_pair(user_id=user_id, role="buyer")
    stored = _stored(user_id)
    refresh_repo = _StubRefreshRepo(stored)
    user_repo = _StubUserRepo(UserCore(id=user_id, role="buyer", verified_status="phone_verified"))
    service = _service(user_repo, refresh_repo)

    result = await service.refresh(refresh_token=tokens.refresh_token)

    assert result.role == "buyer"
    assert result.tokens.refresh_token != tokens.refresh_token
    # Old token burned, new token persisted.
    assert refresh_repo.revoked == [stored.id]
    assert len(refresh_repo.created) == 1
    assert refresh_repo.created[0]["token_hash"] == result.tokens.refresh_token_hash


@pytest.mark.asyncio
async def test_garbage_token_is_invalid() -> None:
    refresh_repo = _StubRefreshRepo(None)
    service = _service(_StubUserRepo(None), refresh_repo)
    with pytest.raises(RefreshTokenInvalid):
        await service.refresh(refresh_token="not-a-jwt")
    assert refresh_repo.revoked == []


@pytest.mark.asyncio
async def test_unknown_hash_is_invalid() -> None:
    user_id = uuid4()
    tokens = _jwt().issue_pair(user_id=user_id, role="buyer")
    # Valid signature, but the token isn't in the store.
    service = _service(_StubUserRepo(None), _StubRefreshRepo(None))
    with pytest.raises(RefreshTokenInvalid):
        await service.refresh(refresh_token=tokens.refresh_token)


@pytest.mark.asyncio
async def test_revoked_token_raises_revoked() -> None:
    user_id = uuid4()
    tokens = _jwt().issue_pair(user_id=user_id, role="buyer")
    refresh_repo = _StubRefreshRepo(_stored(user_id, revoked=True))
    service = _service(_StubUserRepo(None), refresh_repo)
    with pytest.raises(RefreshTokenRevoked):
        await service.refresh(refresh_token=tokens.refresh_token)
    assert refresh_repo.revoked == []


@pytest.mark.asyncio
async def test_db_expired_token_raises_expired() -> None:
    user_id = uuid4()
    tokens = _jwt().issue_pair(user_id=user_id, role="buyer")
    refresh_repo = _StubRefreshRepo(_stored(user_id, expired=True))
    service = _service(_StubUserRepo(None), refresh_repo)
    with pytest.raises(RefreshTokenExpired):
        await service.refresh(refresh_token=tokens.refresh_token)


@pytest.mark.asyncio
async def test_inactive_user_is_invalid() -> None:
    user_id = uuid4()
    tokens = _jwt().issue_pair(user_id=user_id, role="buyer")
    refresh_repo = _StubRefreshRepo(_stored(user_id))
    # User row gone / deactivated -> get_active_by_id returns None.
    service = _service(_StubUserRepo(None), refresh_repo)
    with pytest.raises(RefreshTokenInvalid):
        await service.refresh(refresh_token=tokens.refresh_token)
    assert refresh_repo.revoked == []
