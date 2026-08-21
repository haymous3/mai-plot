"""OtpResendService with mocked repos + adapters (SCRUM-176).

The properties under test are mostly NEGATIVE — what the service must not
reveal. Resend answers identically for an unknown number, an already
verified account and a failed send, so none of them can be used to probe
which Nigerian numbers hold Maiplot accounts.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.twilio import InMemoryTwilioClient
from app.services.otp import verify_code
from app.services.otp_resend import OtpResendService
from app.services.rate_limit import RateLimitResult
from app.services.registration import VerificationRateLimited

_PHONE = "+2348012345678"
_OTP_EXPIRE_MINUTES = 5


class _StubUser:
    def __init__(self, verified_status: str = "unverified") -> None:
        self.id = uuid4()
        self.role = "buyer"
        self.verified_status = verified_status


class _StubUserRepo:
    def __init__(self, user: _StubUser | None) -> None:
        self._user = user

    async def get_by_phone(self, phone: str) -> Any:
        return self._user


class _StubOtpRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.invalidated: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()

    async def invalidate_active(self, **kwargs: Any) -> None:
        self.invalidated.append(kwargs)


class _StubLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed
        self.keys: list[str] = []

    async def check_and_record(self, key: str) -> RateLimitResult:
        self.keys.append(key)
        return RateLimitResult(allowed=self._allowed, remaining=4 if self._allowed else 0)


def _build(
    *,
    user: _StubUser | None = None,
    otp_repo: _StubOtpRepo | None = None,
    limiter: _StubLimiter | None = None,
    sms: InMemoryTwilioClient | None = None,
) -> OtpResendService:
    return OtpResendService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        otps=otp_repo or _StubOtpRepo(),  # type: ignore[arg-type]
        sms=sms or InMemoryTwilioClient(),
        rate_limiter=limiter or _StubLimiter(),  # type: ignore[arg-type]
        otp_expire_minutes=_OTP_EXPIRE_MINUTES,
    )


@pytest.mark.asyncio
async def test_sends_a_fresh_code_and_supersedes_the_old() -> None:
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build(user=_StubUser(), otp_repo=otp_repo, sms=sms)

    await service.resend(phone=_PHONE)

    # The previous code is burnt before the new one is written — otherwise
    # get_active would leave the old code live for the rest of its window.
    assert otp_repo.invalidated == [{"phone": _PHONE, "purpose": "registration"}]
    assert len(otp_repo.created) == 1
    assert otp_repo.created[0]["phone"] == _PHONE
    assert otp_repo.created[0]["purpose"] == "registration"
    assert isinstance(otp_repo.created[0]["expires_at"], datetime)

    assert len(sms.sent) == 1
    assert sms.sent[0].phone == _PHONE


@pytest.mark.asyncio
async def test_sms_carries_a_code_matching_the_stored_hash() -> None:
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build(user=_StubUser(), otp_repo=otp_repo, sms=sms)

    await service.resend(phone=_PHONE)

    match = re.search(r"\b(\d{6})\b", sms.sent[0].message)
    assert match is not None
    code = match.group(1)
    stored = otp_repo.created[0]["code_hash"]
    assert stored != code
    assert stored.startswith("$2")
    assert verify_code(code, stored)


@pytest.mark.asyncio
async def test_unknown_number_is_a_silent_noop() -> None:
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build(user=None, otp_repo=otp_repo, sms=sms)

    await service.resend(phone=_PHONE)  # must NOT raise

    assert otp_repo.created == []
    assert otp_repo.invalidated == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_already_verified_account_is_a_silent_noop() -> None:
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build(user=_StubUser("phone_verified"), otp_repo=otp_repo, sms=sms)

    await service.resend(phone=_PHONE)

    assert otp_repo.created == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_sms_failure_does_not_raise() -> None:
    """A send failure must not leak that this number exists and is
    unverified — the route still answers with the generic 202."""
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient(fail_next=True)
    service = _build(user=_StubUser(), otp_repo=otp_repo, sms=sms)

    await service.resend(phone=_PHONE)  # must NOT raise

    # The code was still committed, so the user can retry.
    assert len(otp_repo.created) == 1


@pytest.mark.asyncio
async def test_rate_limit_is_checked_before_the_user_lookup() -> None:
    """Otherwise a rate-limited caller could still time the lookup to learn
    whether the number exists."""
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    limiter = _StubLimiter(allowed=False)
    service = _build(user=_StubUser(), otp_repo=otp_repo, limiter=limiter, sms=sms)

    with pytest.raises(VerificationRateLimited):
        await service.resend(phone=_PHONE)

    assert limiter.keys == [_PHONE]
    assert otp_repo.created == []
    assert otp_repo.invalidated == []
    assert sms.sent == []
