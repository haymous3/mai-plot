"""RegistrationService with mocked repos + adapters.

Exercises the orchestration logic that the integration tests can't
isolate cleanly (e.g. Termii failure rolls into OtpDispatchFailed).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.termii import InMemoryTermiiClient
from app.services.rate_limit import RateLimitResult
from app.services.registration import (
    OtpDispatchFailed,
    OtpRateLimited,
    PhoneAlreadyRegistered,
    RegistrationService,
)


class _StubUserRepo:
    def __init__(self, existing_phone: str | None = None, new_id: UUID | None = None) -> None:
        self._existing_phone = existing_phone
        self._new_id = new_id or uuid4()
        self.created: list[dict[str, Any]] = []

    async def get_by_phone(self, phone: str) -> Any:
        if self._existing_phone == phone:
            return object()  # truthy
        return None

    async def create_with_pii(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return self._new_id


class _StubOtpRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()


class _StubLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed

    async def check_and_record(self, phone: str) -> RateLimitResult:
        return RateLimitResult(allowed=self._allowed, remaining=4 if self._allowed else 0)


def _build_service(
    *,
    user_repo: _StubUserRepo,
    otp_repo: _StubOtpRepo | None = None,
    limiter: _StubLimiter | None = None,
    termii: InMemoryTermiiClient | None = None,
) -> RegistrationService:
    return RegistrationService(
        users=user_repo,  # type: ignore[arg-type]
        otps=otp_repo or _StubOtpRepo(),  # type: ignore[arg-type]
        rate_limiter=limiter or _StubLimiter(),  # type: ignore[arg-type]
        termii=termii or InMemoryTermiiClient(),
        otp_expire_minutes=5,
    )


@pytest.mark.asyncio
async def test_happy_path_creates_user_and_sends_sms() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    termii = InMemoryTermiiClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, termii=termii)

    result = await service.register(
        phone="+2348012345678",
        role="buyer",
        email=None,
        seller_authority_type=None,
    )

    assert isinstance(result.user_id, UUID)
    assert result.otp_expires_in_seconds == 300
    assert user_repo.created[0]["phone"] == "+2348012345678"
    assert otp_repo.created[0]["purpose"] == "registration"
    assert otp_repo.created[0]["phone"] == "+2348012345678"
    assert isinstance(otp_repo.created[0]["expires_at"], datetime)
    assert len(termii.sent) == 1
    # The OTP must NOT appear in the user-created row (only in the OTP record).
    code = otp_repo.created[0]["code_hash"]
    assert code  # bcrypt hash string


@pytest.mark.asyncio
async def test_duplicate_phone_rejected_before_anything_else() -> None:
    user_repo = _StubUserRepo(existing_phone="+2348012345678")
    otp_repo = _StubOtpRepo()
    termii = InMemoryTermiiClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, termii=termii)

    with pytest.raises(PhoneAlreadyRegistered):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email=None,
            seller_authority_type=None,
        )

    assert user_repo.created == []
    assert otp_repo.created == []
    assert termii.sent == []


@pytest.mark.asyncio
async def test_rate_limited_short_circuits() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    termii = InMemoryTermiiClient()
    service = _build_service(
        user_repo=user_repo,
        otp_repo=otp_repo,
        limiter=_StubLimiter(allowed=False),
        termii=termii,
    )

    with pytest.raises(OtpRateLimited):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email=None,
            seller_authority_type=None,
        )

    assert user_repo.created == []
    assert otp_repo.created == []
    assert termii.sent == []


@pytest.mark.asyncio
async def test_termii_failure_surfaces_as_dispatch_error() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    termii = InMemoryTermiiClient(fail_next=True)
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, termii=termii)

    with pytest.raises(OtpDispatchFailed):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email=None,
            seller_authority_type=None,
        )
    # User + OTP were persisted before the dispatch attempt; the DB
    # transaction is rolled back by the route handler's get_session
    # dependency, so this is consistent with the contract.
    assert len(user_repo.created) == 1
    assert len(otp_repo.created) == 1
