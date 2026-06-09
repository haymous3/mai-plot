"""LogoutService — revokes only the caller's own refresh token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.refresh_token_repo import StoredRefreshToken
from app.services.jwt_service import JwtService
from app.services.logout import LogoutService

SECRET = "test-secret-please-ignore-must-be-long-enough"
ISSUER = "maiplot-platform"


def _jwt() -> JwtService:
    return JwtService(secret=SECRET, issuer=ISSUER, access_expire_minutes=15, refresh_expire_days=7)


class _StubRefreshRepo:
    def __init__(self, stored: StoredRefreshToken | None) -> None:
        self._stored = stored
        self.revoked: list[UUID] = []

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        return self._stored

    async def revoke(self, token_id: UUID) -> None:
        self.revoked.append(token_id)


def _service(repo: _StubRefreshRepo) -> LogoutService:
    return LogoutService(refresh_tokens=repo, jwt=_jwt())  # type: ignore[arg-type]


def _stored(user_id: UUID) -> StoredRefreshToken:
    return StoredRefreshToken(
        id=uuid4(),
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        revoked_at=None,
    )


@pytest.mark.asyncio
async def test_revokes_own_token() -> None:
    user_id = uuid4()
    stored = _stored(user_id)
    repo = _StubRefreshRepo(stored)
    await _service(repo).logout(user_id=user_id, refresh_token="whatever")
    assert repo.revoked == [stored.id]


@pytest.mark.asyncio
async def test_does_not_revoke_another_users_token() -> None:
    stored = _stored(uuid4())  # belongs to someone else
    repo = _StubRefreshRepo(stored)
    await _service(repo).logout(user_id=uuid4(), refresh_token="whatever")
    assert repo.revoked == []


@pytest.mark.asyncio
async def test_unknown_token_is_noop() -> None:
    repo = _StubRefreshRepo(None)
    await _service(repo).logout(user_id=uuid4(), refresh_token="whatever")
    assert repo.revoked == []
