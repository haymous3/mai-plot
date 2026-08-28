"""ForgotPasswordService + ResetPasswordService with mocked repos (SCRUM-191)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.email_verification import InMemoryEmailClient
from app.repositories.email_verification_repo import ActiveEmailToken
from app.repositories.user_repo import UserCore
from app.services.password import verify_password
from app.services.password_reset import (
    PASSWORD_RESET_PURPOSE,
    ForgotPasswordService,
    PasswordResetRateLimited,
    ResetPasswordService,
    ResetTokenExpired,
    ResetTokenInvalid,
)
from app.services.rate_limit import RateLimitResult
from app.services.set_password import WeakPassword

_EMAIL = "buyer@example.com"
_BASE_URL = "https://www.maihomme.com/reset-password"
_STRONG = "NewPassw0rd"


class _StubUserRepo:
    def __init__(self, user: UserCore | None) -> None:
        self._user = user
        self.looked_up: list[str] = []

    async def get_active_by_email(self, email: str) -> UserCore | None:
        self.looked_up.append(email)
        return self._user

    async def get_active_by_id(self, user_id: UUID) -> UserCore | None:
        return self._user


class _StubTokenRepo:
    def __init__(self, active: ActiveEmailToken | None = None) -> None:
        self.active = active
        self.created: list[dict[str, Any]] = []
        self.invalidated: list[dict[str, Any]] = []
        self.marked_used: list[UUID] = []
        self.lookups: list[dict[str, str]] = []

    async def invalidate_active(self, *, user_id: UUID, purpose: str) -> None:
        self.invalidated.append({"user_id": user_id, "purpose": purpose})

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()

    async def get_active_by_hash(self, *, token_hash: str, purpose: str) -> ActiveEmailToken | None:
        self.lookups.append({"token_hash": token_hash, "purpose": purpose})
        return self.active

    async def mark_used(self, token_id: UUID) -> None:
        self.marked_used.append(token_id)
        # The row is single-use: once burnt it no longer satisfies a lookup.
        self.active = None


class _StubCredentialsRepo:
    def __init__(self) -> None:
        self.upserted: list[dict[str, Any]] = []

    async def upsert(self, *, user_id: UUID, password_hash: str) -> None:
        self.upserted.append({"user_id": user_id, "password_hash": password_hash})


class _StubRefreshRepo:
    def __init__(self) -> None:
        self.revoked_for: list[UUID] = []

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        self.revoked_for.append(user_id)


class _StubLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed
        self.keys: list[str] = []

    async def check_and_record(self, key: str) -> RateLimitResult:
        self.keys.append(key)
        return RateLimitResult(allowed=self._allowed, remaining=4 if self._allowed else 0)


def _user(verified_status: str = "email_verified") -> UserCore:
    return UserCore(id=uuid4(), role="buyer", verified_status=verified_status)


def _build_forgot(
    *,
    user: UserCore | None,
    limiter: _StubLimiter | None = None,
    email: InMemoryEmailClient | None = None,
) -> tuple[ForgotPasswordService, _StubTokenRepo, _StubLimiter, InMemoryEmailClient]:
    tokens = _StubTokenRepo()
    lim = limiter or _StubLimiter()
    sender = email or InMemoryEmailClient()
    service = ForgotPasswordService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        tokens=tokens,  # type: ignore[arg-type]
        email_sender=sender,
        rate_limiter=lim,  # type: ignore[arg-type]
        reset_expire_minutes=15,
        reset_base_url=_BASE_URL,
    )
    return service, tokens, lim, sender


def _build_reset(
    *,
    user: UserCore | None,
    active: ActiveEmailToken | None,
) -> tuple[ResetPasswordService, _StubTokenRepo, _StubCredentialsRepo, _StubRefreshRepo]:
    tokens = _StubTokenRepo(active)
    creds = _StubCredentialsRepo()
    refresh = _StubRefreshRepo()
    service = ResetPasswordService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        tokens=tokens,  # type: ignore[arg-type]
        credentials=creds,  # type: ignore[arg-type]
        refresh_tokens=refresh,  # type: ignore[arg-type]
    )
    return service, tokens, creds, refresh


def _active(user_id: UUID, *, minutes: int = 15) -> ActiveEmailToken:
    return ActiveEmailToken(
        id=uuid4(),
        user_id=user_id,
        email=_EMAIL,
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )


# ── ForgotPasswordService ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_known_email_gets_a_reset_link() -> None:
    user = _user()
    service, tokens, lim, email = _build_forgot(user=user)

    await service.request(email=_EMAIL)

    assert tokens.invalidated == [{"user_id": user.id, "purpose": PASSWORD_RESET_PURPOSE}]
    assert len(tokens.created) == 1
    assert tokens.created[0]["purpose"] == PASSWORD_RESET_PURPOSE
    assert len(tokens.created[0]["token_hash"]) == 64
    assert len(email.sent_password_resets) == 1
    assert email.sent_password_resets[0].to == _EMAIL
    assert email.sent_password_resets[0].reset_url.startswith(f"{_BASE_URL}?token=")
    # Never sent as a verification mail — the two are separate channels.
    assert email.sent == []
    assert lim.keys == [_EMAIL]


@pytest.mark.asyncio
async def test_unknown_email_is_a_silent_noop() -> None:
    service, tokens, _, email = _build_forgot(user=None)

    await service.request(email=_EMAIL)

    assert tokens.created == []
    assert tokens.invalidated == []
    assert email.sent_password_resets == []


@pytest.mark.asyncio
async def test_an_unverified_account_can_still_reset() -> None:
    # Deliberate: /auth/verify/email/resend already turns an unverified address
    # into a full session, so gating reset on verification buys nothing.
    service, tokens, _, email = _build_forgot(user=_user(verified_status="unverified"))

    await service.request(email=_EMAIL)

    assert len(tokens.created) == 1
    assert len(email.sent_password_resets) == 1


@pytest.mark.asyncio
async def test_a_phone_only_account_can_still_reset() -> None:
    # The class of user this ticket exists for: verified by OTP, no password
    # row at all, and no way back in while SMS to Nigeria is unavailable.
    service, tokens, _, email = _build_forgot(user=_user(verified_status="phone_verified"))

    await service.request(email=_EMAIL)

    assert len(tokens.created) == 1
    assert len(email.sent_password_resets) == 1


@pytest.mark.asyncio
async def test_rate_limited_raises_before_any_work() -> None:
    service, tokens, _, email = _build_forgot(user=_user(), limiter=_StubLimiter(allowed=False))

    with pytest.raises(PasswordResetRateLimited):
        await service.request(email=_EMAIL)

    assert tokens.created == []
    assert email.sent_password_resets == []


@pytest.mark.asyncio
async def test_unknown_email_is_rate_limited_too() -> None:
    # The limiter runs BEFORE the lookup, so an address with no account burns
    # budget on exactly the same schedule as a real one. If this ever inverts,
    # response timing starts to distinguish the two.
    service, _, lim, _ = _build_forgot(user=None)

    await service.request(email=_EMAIL)

    assert lim.keys == [_EMAIL]


@pytest.mark.asyncio
async def test_send_failure_is_swallowed_but_token_persists() -> None:
    service, tokens, _, _ = _build_forgot(user=_user(), email=InMemoryEmailClient(fail_next=True))

    await service.request(email=_EMAIL)  # does not raise

    assert len(tokens.created) == 1


# ── ResetPasswordService ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_token_sets_the_password_and_revokes_sessions() -> None:
    user = _user()
    record = _active(user.id)
    service, tokens, creds, refresh = _build_reset(user=user, active=record)

    await service.reset(token="raw-token", new_password=_STRONG)

    assert tokens.lookups[0]["purpose"] == PASSWORD_RESET_PURPOSE
    assert tokens.marked_used == [record.id]
    assert len(creds.upserted) == 1
    assert creds.upserted[0]["user_id"] == user.id
    # Stored as a bcrypt hash, never the plaintext.
    assert creds.upserted[0]["password_hash"] != _STRONG
    assert verify_password(_STRONG, creds.upserted[0]["password_hash"])
    assert refresh.revoked_for == [user.id]


@pytest.mark.asyncio
async def test_token_is_single_use() -> None:
    user = _user()
    service, _, creds, _ = _build_reset(user=user, active=_active(user.id))

    await service.reset(token="raw-token", new_password=_STRONG)
    with pytest.raises(ResetTokenInvalid):
        await service.reset(token="raw-token", new_password="OtherPass1")

    assert len(creds.upserted) == 1


@pytest.mark.asyncio
async def test_unknown_token_is_invalid() -> None:
    service, _, creds, refresh = _build_reset(user=_user(), active=None)

    with pytest.raises(ResetTokenInvalid):
        await service.reset(token="nope", new_password=_STRONG)

    assert creds.upserted == []
    assert refresh.revoked_for == []


@pytest.mark.asyncio
async def test_expired_token_is_rejected() -> None:
    user = _user()
    service, tokens, creds, _ = _build_reset(user=user, active=_active(user.id, minutes=-1))

    with pytest.raises(ResetTokenExpired):
        await service.reset(token="raw-token", new_password=_STRONG)

    assert tokens.marked_used == []
    assert creds.upserted == []


@pytest.mark.asyncio
async def test_naive_expiry_is_treated_as_utc() -> None:
    # SQLite (and some drivers) hand back a naive datetime; without the guard a
    # comparison against an aware now() raises TypeError -> 500.
    user = _user()
    naive = ActiveEmailToken(
        id=uuid4(),
        user_id=user.id,
        email=_EMAIL,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10),
    )
    service, _, creds, _ = _build_reset(user=user, active=naive)

    await service.reset(token="raw-token", new_password=_STRONG)

    assert len(creds.upserted) == 1


@pytest.mark.asyncio
async def test_weak_password_is_rejected_after_the_token_checks_out() -> None:
    # Order matters: composition is checked only once the token proves valid, so
    # a junk password cannot be used to probe whether a token is live.
    user = _user()
    service, tokens, creds, refresh = _build_reset(user=user, active=_active(user.id))

    with pytest.raises(WeakPassword):
        await service.reset(token="raw-token", new_password="short")

    # Token NOT burnt — the user retries with a stronger password on the same link.
    assert tokens.marked_used == []
    assert creds.upserted == []
    assert refresh.revoked_for == []


@pytest.mark.asyncio
async def test_weak_password_on_a_bad_token_reports_the_token_not_the_password() -> None:
    service, _, creds, _ = _build_reset(user=_user(), active=None)

    with pytest.raises(ResetTokenInvalid):
        await service.reset(token="nope", new_password="short")

    assert creds.upserted == []


@pytest.mark.asyncio
async def test_token_for_a_vanished_account_is_invalid() -> None:
    # Account soft-deleted between requesting the link and clicking it.
    service, tokens, creds, _ = _build_reset(user=None, active=_active(uuid4()))

    with pytest.raises(ResetTokenInvalid):
        await service.reset(token="raw-token", new_password=_STRONG)

    assert tokens.marked_used == []
    assert creds.upserted == []
