"""RegistrationService with mocked repos + adapters (email flow, SCRUM-152).

Exercises the orchestration logic the integration tests can't isolate
cleanly (e.g. an email-delivery failure rolls into VerificationEmailFailed,
and the duplicate/rate-limit short-circuits happen before any write).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.email_verification import InMemoryEmailClient
from app.services.rate_limit import RateLimitResult
from app.services.registration import (
    EmailAlreadyRegistered,
    PhoneAlreadyRegistered,
    RegistrationService,
    VerificationEmailFailed,
    VerificationRateLimited,
)

_BASE_URL = "https://app.maiplot.ng/verify-email"


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


class _StubEmailTokenRepo:
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


def _build_service(
    *,
    user_repo: _StubUserRepo,
    token_repo: _StubEmailTokenRepo | None = None,
    creds_repo: _StubCredsRepo | None = None,
    limiter: _StubLimiter | None = None,
    email_sender: InMemoryEmailClient | None = None,
) -> RegistrationService:
    return RegistrationService(
        users=user_repo,  # type: ignore[arg-type]
        email_tokens=token_repo or _StubEmailTokenRepo(),  # type: ignore[arg-type]
        credentials=creds_repo or _StubCredsRepo(),  # type: ignore[arg-type]
        rate_limiter=limiter or _StubLimiter(),  # type: ignore[arg-type]
        email_sender=email_sender or InMemoryEmailClient(),
        verification_expire_minutes=30,
        verify_base_url=_BASE_URL,
    )


@pytest.mark.asyncio
async def test_happy_path_creates_user_and_sends_email() -> None:
    user_repo = _StubUserRepo()
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient()
    service = _build_service(user_repo=user_repo, token_repo=token_repo, email_sender=email)

    result = await service.register(
        phone="+2348012345678",
        role="buyer",
        email="buyer@example.com",
        password=None,
        seller_authority_type=None,
    )

    assert isinstance(result.user_id, UUID)
    assert result.verification_expires_in_seconds == 30 * 60
    assert user_repo.created[0]["phone"] == "+2348012345678"
    assert user_repo.created[0]["email"] == "buyer@example.com"

    assert token_repo.created[0]["purpose"] == "registration"
    assert token_repo.created[0]["email"] == "buyer@example.com"
    assert isinstance(token_repo.created[0]["expires_at"], datetime)
    # The persisted value is the SHA-256 hash (64 hex chars), never the token.
    token_hash = token_repo.created[0]["token_hash"]
    assert len(token_hash) == 64

    assert len(email.sent) == 1
    sent = email.sent[0]
    assert sent.to == "buyer@example.com"
    # The magic link points at the configured landing page and carries a token.
    assert sent.verify_url.startswith(f"{_BASE_URL}?token=")
    # The raw token is in the link but must NOT equal the stored hash.
    raw_token = sent.verify_url.split("token=", 1)[1]
    assert raw_token and raw_token != token_hash


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
    )

    assert creds_repo.upserted == []


@pytest.mark.asyncio
async def test_duplicate_email_rejected_before_anything_else() -> None:
    user_repo = _StubUserRepo(existing_email="buyer@example.com")
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient()
    service = _build_service(user_repo=user_repo, token_repo=token_repo, email_sender=email)

    with pytest.raises(EmailAlreadyRegistered):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
        )

    assert user_repo.created == []
    assert token_repo.created == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_duplicate_phone_rejected() -> None:
    user_repo = _StubUserRepo(existing_phone="+2348012345678")
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient()
    service = _build_service(user_repo=user_repo, token_repo=token_repo, email_sender=email)

    with pytest.raises(PhoneAlreadyRegistered):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
        )

    assert user_repo.created == []
    assert token_repo.created == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_rate_limited_short_circuits_and_keys_on_email() -> None:
    user_repo = _StubUserRepo()
    token_repo = _StubEmailTokenRepo()
    email = InMemoryEmailClient()
    limiter = _StubLimiter(allowed=False)
    service = _build_service(
        user_repo=user_repo, token_repo=token_repo, limiter=limiter, email_sender=email
    )

    with pytest.raises(VerificationRateLimited):
        await service.register(
            phone="+2348012345678",
            role="buyer",
            email="buyer@example.com",
            password=None,
            seller_authority_type=None,
        )

    # The limiter is keyed on the email address, not the phone.
    assert limiter.keys == ["buyer@example.com"]
    assert user_repo.created == []
    assert token_repo.created == []
    assert email.sent == []


@pytest.mark.asyncio
async def test_email_delivery_failure_surfaces_as_verification_error() -> None:
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
        )
    # User + token were persisted before the send attempt; the DB transaction
    # is rolled back by the route handler's get_session dependency, so this is
    # consistent with the contract.
    assert len(user_repo.created) == 1
    assert len(token_repo.created) == 1
