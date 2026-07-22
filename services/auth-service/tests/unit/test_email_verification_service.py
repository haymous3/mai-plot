"""EmailVerificationService.verify with mocked repos (SCRUM-152)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.repositories.email_verification_repo import ActiveEmailToken
from app.repositories.user_repo import UserCore
from app.services.email_token import hash_token
from app.services.email_verification import (
    EmailTokenExpired,
    EmailTokenInvalid,
    EmailVerificationService,
)
from app.services.jwt_service import JwtService

_TOKEN = "a-magic-link-token"


class _StubTokenRepo:
    def __init__(self, record: ActiveEmailToken | None) -> None:
        self._record = record
        self.marked_used: list[UUID] = []
        self.lookups: list[tuple[str, str]] = []

    async def get_active_by_hash(self, *, token_hash: str, purpose: str) -> ActiveEmailToken | None:
        self.lookups.append((token_hash, purpose))
        # Only return the record when the hash + purpose actually match, so the
        # test exercises the same guard the real query applies.
        if self._record is None:
            return None
        if token_hash == hash_token(_TOKEN) and purpose == "registration":
            return self._record
        return None

    async def mark_used(self, token_id: UUID) -> None:
        self.marked_used.append(token_id)


class _StubUserRepo:
    def __init__(self, user: UserCore | None) -> None:
        self._user = user
        self.verified: list[UUID] = []

    async def get_active_by_id(self, user_id: UUID) -> UserCore | None:
        return self._user

    async def mark_email_verified(self, user_id: UUID) -> None:
        self.verified.append(user_id)


class _StubRefreshRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()


def _jwt() -> JwtService:
    return JwtService(
        secret="test-secret-at-least-32-bytes-long!!",
        issuer="maiplot-platform",
        access_expire_minutes=15,
        refresh_expire_days=7,
    )


def _service(
    *, token_repo: _StubTokenRepo, user_repo: _StubUserRepo, refresh_repo: _StubRefreshRepo
) -> EmailVerificationService:
    return EmailVerificationService(
        users=user_repo,  # type: ignore[arg-type]
        tokens=token_repo,  # type: ignore[arg-type]
        refresh_tokens=refresh_repo,  # type: ignore[arg-type]
        jwt=_jwt(),
    )


@pytest.mark.asyncio
async def test_verify_happy_path_marks_used_and_verifies() -> None:
    user_id = uuid4()
    record = ActiveEmailToken(
        id=uuid4(),
        user_id=user_id,
        email="buyer@example.com",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    token_repo = _StubTokenRepo(record)
    user_repo = _StubUserRepo(UserCore(id=user_id, role="buyer", verified_status="unverified"))
    refresh_repo = _StubRefreshRepo()
    service = _service(token_repo=token_repo, user_repo=user_repo, refresh_repo=refresh_repo)

    result = await service.verify(token=_TOKEN, purpose="registration")

    assert result.user_id == user_id
    assert result.role == "buyer"
    assert result.verified_status == "email_verified"
    assert result.tokens.access_token
    assert token_repo.marked_used == [record.id]
    assert user_repo.verified == [user_id]
    assert len(refresh_repo.created) == 1
    # The lookup used the SHA-256 hash of the token, never the token itself.
    assert token_repo.lookups[0][0] == hash_token(_TOKEN)


@pytest.mark.asyncio
async def test_verify_unknown_token_raises_invalid() -> None:
    token_repo = _StubTokenRepo(None)
    user_repo = _StubUserRepo(UserCore(id=uuid4(), role="buyer", verified_status="unverified"))
    service = _service(token_repo=token_repo, user_repo=user_repo, refresh_repo=_StubRefreshRepo())
    with pytest.raises(EmailTokenInvalid):
        await service.verify(token=_TOKEN, purpose="registration")


@pytest.mark.asyncio
async def test_verify_expired_token_raises_expired() -> None:
    user_id = uuid4()
    record = ActiveEmailToken(
        id=uuid4(),
        user_id=user_id,
        email="buyer@example.com",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    token_repo = _StubTokenRepo(record)
    user_repo = _StubUserRepo(UserCore(id=user_id, role="buyer", verified_status="unverified"))
    service = _service(token_repo=token_repo, user_repo=user_repo, refresh_repo=_StubRefreshRepo())
    with pytest.raises(EmailTokenExpired):
        await service.verify(token=_TOKEN, purpose="registration")
    # An expired link is never burnt (so a re-send can reuse the row cleanup).
    assert token_repo.marked_used == []


@pytest.mark.asyncio
async def test_verify_missing_user_raises_invalid() -> None:
    record = ActiveEmailToken(
        id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.com",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    token_repo = _StubTokenRepo(record)
    user_repo = _StubUserRepo(None)  # user gone between register and verify
    service = _service(token_repo=token_repo, user_repo=user_repo, refresh_repo=_StubRefreshRepo())
    with pytest.raises(EmailTokenInvalid):
        await service.verify(token=_TOKEN, purpose="registration")


@pytest.mark.asyncio
async def test_verify_preserves_higher_status() -> None:
    # A user already id_verified who confirms email keeps the higher status in
    # the reported result (mark_email_verified only lifts 'unverified').
    user_id = uuid4()
    record = ActiveEmailToken(
        id=uuid4(),
        user_id=user_id,
        email="buyer@example.com",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    token_repo = _StubTokenRepo(record)
    user_repo = _StubUserRepo(UserCore(id=user_id, role="buyer", verified_status="id_verified"))
    service = _service(token_repo=token_repo, user_repo=user_repo, refresh_repo=_StubRefreshRepo())
    result = await service.verify(token=_TOKEN, purpose="registration")
    assert result.verified_status == "id_verified"
