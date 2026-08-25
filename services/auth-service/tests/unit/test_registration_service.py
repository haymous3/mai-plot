"""RegistrationService with mocked repos + adapters (phone OTP flow, SCRUM-175).

Exercises the orchestration logic the integration tests can't isolate
cleanly (e.g. an SMS-delivery failure rolls into OtpDispatchFailed, and the
duplicate/rate-limit short-circuits happen before any write).

SCRUM-175 reverted the verification channel from the SCRUM-152 email magic
link back to phone OTP over SMS, now dispatched via Twilio.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.email_verification import InMemoryEmailClient
from app.adapters.twilio import InMemoryTwilioClient
from app.services.otp import verify_code
from app.services.rate_limit import RateLimitResult
from app.services.registration import (
    EmailAlreadyRegistered,
    OtpDispatchFailed,
    PhoneAlreadyRegistered,
    RegistrationService,
    VerificationEmailFailed,
    VerificationRateLimited,
)

_OTP_EXPIRE_MINUTES = 5
_EMAIL_EXPIRE_MINUTES = 30
_VERIFY_BASE_URL = "https://app.maiplot.ng/verify-email"


class _StubUserRepo:
    def __init__(
        self,
        existing_phone: str | None = None,
        existing_email: str | None = None,
        new_id: UUID | None = None,
    ) -> None:
        self._existing_phone = existing_phone
        self._existing_email = existing_email
        self._new_id = new_id or uuid4()
        self.created: list[dict[str, Any]] = []

    async def get_by_phone(self, phone: str) -> Any:
        return object() if self._existing_phone == phone else None

    async def get_active_by_email(self, email: str) -> Any:
        return object() if self._existing_email == email else None

    async def create_with_pii(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return self._new_id


class _StubOtpRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()


class _StubCredsRepo:
    def __init__(self) -> None:
        self.upserted: list[dict[str, Any]] = []

    async def upsert(self, **kwargs: Any) -> None:
        self.upserted.append(kwargs)


class _StubLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed
        self.keys: list[str] = []

    async def check_and_record(self, key: str) -> RateLimitResult:
        self.keys.append(key)
        return RateLimitResult(allowed=self._allowed, remaining=4 if self._allowed else 0)


class _StubEmailTokenRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> UUID:
        self.created.append(kwargs)
        return uuid4()


def _build_service(
    *,
    user_repo: _StubUserRepo,
    otp_repo: _StubOtpRepo | None = None,
    token_repo: _StubEmailTokenRepo | None = None,
    creds_repo: _StubCredsRepo | None = None,
    limiter: _StubLimiter | None = None,
    sms: InMemoryTwilioClient | None = None,
    email_sender: InMemoryEmailClient | None = None,
) -> RegistrationService:
    return RegistrationService(
        users=user_repo,  # type: ignore[arg-type]
        otps=otp_repo or _StubOtpRepo(),  # type: ignore[arg-type]
        email_tokens=token_repo or _StubEmailTokenRepo(),  # type: ignore[arg-type]
        credentials=creds_repo or _StubCredsRepo(),  # type: ignore[arg-type]
        rate_limiter=limiter or _StubLimiter(),  # type: ignore[arg-type]
        sms=sms or InMemoryTwilioClient(),
        email_sender=email_sender or InMemoryEmailClient(),
        otp_expire_minutes=_OTP_EXPIRE_MINUTES,
        email_expire_minutes=_EMAIL_EXPIRE_MINUTES,
        verify_base_url=_VERIFY_BASE_URL,
    )


@pytest.mark.asyncio
async def test_happy_path_creates_user_and_sends_otp() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, sms=sms)

    result = await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="phone",
    )

    assert isinstance(result.user_id, UUID)
    assert result.verification_expires_in_seconds == _OTP_EXPIRE_MINUTES * 60
    assert user_repo.created[0]["phone"] == "+2348012345678"
    # Email is still collected and stored — it is the login identifier even
    # though it is no longer the verification channel.
    assert user_repo.created[0]["email"] == "buyer@example.com"

    assert otp_repo.created[0]["purpose"] == "registration"
    assert otp_repo.created[0]["phone"] == "+2348012345678"
    assert isinstance(otp_repo.created[0]["expires_at"], datetime)

    assert len(sms.sent) == 1
    assert sms.sent[0].phone == "+2348012345678"


@pytest.mark.asyncio
async def test_sms_carries_a_six_digit_code_matching_the_stored_hash() -> None:
    """The plaintext code exists only in the SMS; the DB holds a bcrypt hash.
    This is the whole security property of the OTP flow (CLAUDE.md §4)."""
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, sms=sms)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="phone",
    )

    match = re.search(r"\b(\d{6})\b", sms.sent[0].message)
    assert match is not None, f"no 6-digit code in {sms.sent[0].message!r}"
    code = match.group(1)

    stored_hash = otp_repo.created[0]["code_hash"]
    assert stored_hash != code
    assert stored_hash.startswith("$2")
    assert verify_code(code, stored_hash)


@pytest.mark.asyncio
async def test_full_name_is_passed_to_user_creation() -> None:
    user_repo = _StubUserRepo()
    service = _build_service(user_repo=user_repo)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        full_name="Ada Obi",
    )

    assert user_repo.created[0]["full_name"] == "Ada Obi"


@pytest.mark.asyncio
async def test_absent_full_name_persists_empty_string() -> None:
    user_repo = _StubUserRepo()
    service = _build_service(user_repo=user_repo)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="phone",
    )

    # create_with_pii is called with "" (not None) so the column stays non-null.
    assert user_repo.created[0]["full_name"] == ""


@pytest.mark.asyncio
async def test_password_is_hashed_and_stored_when_provided() -> None:
    user_repo = _StubUserRepo()
    creds_repo = _StubCredsRepo()
    service = _build_service(user_repo=user_repo, creds_repo=creds_repo)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password="SecurePass123!",
        seller_authority_type=None,
        verification_channel="phone",
    )

    assert len(creds_repo.upserted) == 1
    stored = creds_repo.upserted[0]["password_hash"]
    # Stored as a bcrypt hash, never the plaintext.
    assert stored != "SecurePass123!"
    assert stored.startswith("$2")


@pytest.mark.asyncio
async def test_password_skipped_when_absent() -> None:
    user_repo = _StubUserRepo()
    creds_repo = _StubCredsRepo()
    service = _build_service(user_repo=user_repo, creds_repo=creds_repo)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="phone",
    )

    assert creds_repo.upserted == []


@pytest.mark.asyncio
async def test_duplicate_email_rejected_before_anything_else() -> None:
    user_repo = _StubUserRepo(existing_email="buyer@example.com")
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, sms=sms)

    with pytest.raises(EmailAlreadyRegistered):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
            verification_channel="phone",
        )

    assert user_repo.created == []
    assert otp_repo.created == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_duplicate_phone_rejected() -> None:
    user_repo = _StubUserRepo(existing_phone="+2348012345678")
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, sms=sms)

    with pytest.raises(PhoneAlreadyRegistered):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
            verification_channel="phone",
        )

    assert user_repo.created == []
    assert otp_repo.created == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_rate_limited_short_circuits_and_keys_on_phone() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient()
    limiter = _StubLimiter(allowed=False)
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, limiter=limiter, sms=sms)

    with pytest.raises(VerificationRateLimited):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
            verification_channel="phone",
        )

    # SCRUM-175: the limiter is keyed on the PHONE again (CLAUDE.md §4 caps OTP
    # sends per phone). It was keyed on email while the magic link was live.
    assert limiter.keys == ["+2348012345678"]
    assert user_repo.created == []
    assert otp_repo.created == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_sms_delivery_failure_surfaces_as_otp_dispatch_failed() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    sms = InMemoryTwilioClient(fail_next=True)
    service = _build_service(user_repo=user_repo, otp_repo=otp_repo, sms=sms)

    with pytest.raises(OtpDispatchFailed):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
            verification_channel="phone",
        )
    # User + OTP were persisted before the send attempt; the DB transaction is
    # rolled back by the route handler's get_session dependency, so this is
    # consistent with the contract.
    assert len(user_repo.created) == 1
    assert len(otp_repo.created) == 1


# --- email channel (SCRUM-180) ---------------------------------------------


@pytest.mark.asyncio
async def test_email_channel_mints_a_link_and_sends_no_sms() -> None:
    user_repo = _StubUserRepo()
    otp_repo = _StubOtpRepo()
    token_repo = _StubEmailTokenRepo()
    sms = InMemoryTwilioClient()
    email = InMemoryEmailClient()
    service = _build_service(
        user_repo=user_repo, otp_repo=otp_repo, token_repo=token_repo, sms=sms, email_sender=email
    )

    result = await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="email",
    )

    assert result.verification_channel == "email"
    # The link TTL, not the OTP one — the two differ by 25 minutes.
    assert result.verification_expires_in_seconds == _EMAIL_EXPIRE_MINUTES * 60

    assert len(token_repo.created) == 1
    assert token_repo.created[0]["email"] == "buyer@example.com"
    assert token_repo.created[0]["purpose"] == "registration"
    # SHA-256 hex, never the raw token.
    assert len(token_repo.created[0]["token_hash"]) == 64

    assert len(email.sent) == 1
    assert email.sent[0].to == "buyer@example.com"
    assert email.sent[0].verify_url.startswith(f"{_VERIFY_BASE_URL}?token=")

    # The channels are mutually exclusive: no OTP row, no SMS.
    assert otp_repo.created == []
    assert sms.sent == []


@pytest.mark.asyncio
async def test_email_channel_link_carries_a_token_that_is_not_the_stored_hash() -> None:
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient()
    service = _build_service(user_repo=_StubUserRepo(), token_repo=token_repo, email_sender=email)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="email",
    )

    raw = email.sent[0].verify_url.split("token=", 1)[1]
    assert raw
    assert raw != token_repo.created[0]["token_hash"]


@pytest.mark.asyncio
async def test_email_channel_is_the_default() -> None:
    """Omitting the channel must pick email — the one that can reach users."""
    otp_repo = _StubOtpRepo()
    token_repo = _StubEmailTokenRepo()
    service = _build_service(user_repo=_StubUserRepo(), otp_repo=otp_repo, token_repo=token_repo)

    result = await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
    )

    assert result.verification_channel == "email"
    assert len(token_repo.created) == 1
    assert otp_repo.created == []


@pytest.mark.asyncio
async def test_email_channel_rate_limits_on_the_email_not_the_phone() -> None:
    """Each channel spends its own budget — otherwise one could exhaust the
    other's, and the OTP cap is a §4 non-negotiable."""
    limiter = _StubLimiter()
    service = _build_service(user_repo=_StubUserRepo(), limiter=limiter)

    await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
        verification_channel="email",
    )

    assert limiter.keys == ["buyer@example.com"]


@pytest.mark.asyncio
async def test_email_delivery_failure_surfaces_as_verification_email_failed() -> None:
    user_repo = _StubUserRepo()
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient(fail_next=True)
    service = _build_service(user_repo=user_repo, token_repo=token_repo, email_sender=email)

    with pytest.raises(VerificationEmailFailed):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
            verification_channel="email",
        )

    # User + token were written before the send; the route catches this and
    # returns 502, so the session still commits and the account persists.
    # Recovery is POST /auth/verify/email/resend.
    assert len(user_repo.created) == 1
    assert len(token_repo.created) == 1
