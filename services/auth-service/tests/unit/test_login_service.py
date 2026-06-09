"""LoginService with stub repos + a real JwtService."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.user_repo import UserCore
from app.services.jwt_service import JwtService
from app.services.login import InvalidCredentials, LoginService
from app.services.password import hash_password

SECRET = "test-secret-please-ignore-must-be-long-enough"
ISSUER = "maiplot-platform"


def _jwt() -> JwtService:
    return JwtService(secret=SECRET, issuer=ISSUER, access_expire_minutes=15, refresh_expire_days=7)


class _StubUserRepo:
    def __init__(self, user: UserCore | None) -> None:
        self._user = user

    async def get_active_by_email(self, email: str) -> UserCore | None:
        return self._user


class _StubCredsRepo:
    def __init__(self, password_hash: str | None) -> None:
        self._hash = password_hash

    async def get_password_hash(self, user_id: UUID) -> str | None:
        return self._hash


class _StubRefreshRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

    async def create(self, *, user_id: UUID, token_hash: str, expires_at: datetime) -> UUID:
        new_id = uuid4()
        self.created.append({"user_id": user_id, "token_hash": token_hash})
        return new_id


def _service(
    user: UserCore | None, password_hash: str | None, refresh_repo: _StubRefreshRepo
) -> LoginService:
    return LoginService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        credentials=_StubCredsRepo(password_hash),  # type: ignore[arg-type]
        refresh_tokens=refresh_repo,  # type: ignore[arg-type]
        jwt=_jwt(),
    )


@pytest.mark.asyncio
async def test_login_success_issues_and_persists_tokens() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, hash_password("SecurePass123!"), refresh_repo)

    result = await service.login(email="buyer@example.com", password="SecurePass123!")

    assert result.user_id == user.id
    assert result.role == "buyer"
    assert result.tokens.access_token
    assert len(refresh_repo.created) == 1


@pytest.mark.asyncio
async def test_unknown_email_is_invalid() -> None:
    refresh_repo = _StubRefreshRepo()
    service = _service(None, None, refresh_repo)
    with pytest.raises(InvalidCredentials):
        await service.login(email="nobody@example.com", password="whatever12")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_no_password_set_is_invalid() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, None, refresh_repo)  # user exists, no credential
    with pytest.raises(InvalidCredentials):
        await service.login(email="buyer@example.com", password="whatever12")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_wrong_password_is_invalid() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, hash_password("CorrectPass1!"), refresh_repo)
    with pytest.raises(InvalidCredentials):
        await service.login(email="buyer@example.com", password="WrongPass1!")
    assert refresh_repo.created == []
