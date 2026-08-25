"""ResendVerificationService with mocked repos + adapters (SCRUM-154)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.email_verification import InMemoryEmailClient
from app.repositories.user_repo import UserCore
from app.services.rate_limit import RateLimitResult
from app.services.registration import VerificationRateLimited
from app.services.resend_verification import ResendVerificationService

_EMAIL = "buyer@example.com"
_BASE_URL = "https://app.maihomme.com/verify-email"


class _StubUserRepo:
    def __init__(self, user: UserCore | None) -> None:
        self._user = user
        self.looked_up: list[str] = []

    async def get_active_by_email(self, email: str) -> UserCore | None:
        self.looked_up.append(email)
        return self._user


class _StubTokenRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.invalidated: list[dict[str, Any]] = []

    async def invalidate_active(self, *, user_id: UUID, purpose: str) -> None:
        self.invalidated.append({"user_id": user_id, "purpose": purpose})

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()


class _StubLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed
        self.keys: list[str] = []

    async def check_and_record(self, key: str) -> RateLimitResult:
        self.keys.append(key)
        return RateLimitResult(allowed=self._allowed, remaining=4 if self._allowed else 0)


def _unverified(user_id: UUID | None = None) -> UserCore:
    return UserCore(id=user_id or uuid4(), role="buyer", verified_status="unverified")


def _build(
    *,
    user: UserCore | None,
    token_repo: _StubTokenRepo | None = None,
    limiter: _StubLimiter | None = None,
    email: InMemoryEmailClient | None = None,
) -> tuple[ResendVerificationService, _StubTokenRepo, _StubLimiter, InMemoryEmailClient]:
    tokens = token_repo or _StubTokenRepo()
    lim = limiter or _StubLimiter()
    sender = email or InMemoryEmailClient()
    service = ResendVerificationService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        tokens=tokens,  # type: ignore[arg-type]
        email_sender=sender,
        rate_limiter=lim,  # type: ignore[arg-type]
        verification_expire_minutes=30,
        verify_base_url=_BASE_URL,
    )
    return service, tokens, lim, sender


@pytest.mark.asyncio
async def test_unverified_user_gets_a_fresh_link() -> None:
    user = _unverified()
    service, tokens, lim, email = _build(user=user)

    await service.resend(email=_EMAIL)

    # Prior links superseded, a new token minted, and one email sent.
    assert tokens.invalidated == [{"user_id": user.id, "purpose": "registration"}]
    assert len(tokens.created) == 1
    assert tokens.created[0]["purpose"] == "registration"
    assert len(tokens.created[0]["token_hash"]) == 64
    assert len(email.sent) == 1
    assert email.sent[0].to == _EMAIL
    assert email.sent[0].verify_url.startswith(f"{_BASE_URL}?token=")
    # The limiter is keyed on the email.
    assert lim.keys == [_EMAIL]


@pytest.mark.asyncio
async def test_unknown_email_is_a_silent_noop() -> None:
    service, tokens, _, email = _build(user=None)

    await service.resend(email=_EMAIL)

    assert tokens.created == []
    assert tokens.invalidated == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_already_verified_is_a_silent_noop() -> None:
    verified = UserCore(id=uuid4(), role="buyer", verified_status="email_verified")
    service, tokens, _, email = _build(user=verified)

    await service.resend(email=_EMAIL)

    assert tokens.created == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_rate_limited_raises_before_any_work() -> None:
    user = _unverified()
    service, tokens, _, email = _build(user=user, limiter=_StubLimiter(allowed=False))

    with pytest.raises(VerificationRateLimited):
        await service.resend(email=_EMAIL)

    # Denied before the lookup / token mint / send.
    assert tokens.created == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_send_failure_is_swallowed_but_token_persists() -> None:
    # A delivery failure must not leak that the address exists — resend returns
    # normally (the route answers a generic 202). The new token is still minted.
    user = _unverified()
    service, tokens, _, _ = _build(user=user, email=InMemoryEmailClient(fail_next=True))

    await service.resend(email=_EMAIL)  # does not raise

    assert len(tokens.created) == 1
