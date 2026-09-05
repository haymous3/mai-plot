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

    async def get_active_by_id(self, user_id: UUID) -> UserCore | None:
        if self._user is not None and self._user.id == user_id:
            return self._user
        return None


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


class _StubRegistrationRepo:
    """Maps realtor -> issued number, both directions (SCRUM-207)."""

    def __init__(self, issued: dict[UUID, str] | None = None) -> None:
        self._issued = issued or {}

    async def get_for_user(self, user_id: UUID) -> str | None:
        return self._issued.get(user_id)

    async def get_user_id(self, registration_number: str) -> UUID | None:
        for user_id, number in self._issued.items():
            if number == registration_number:
                return user_id
        return None


def _service(
    user: UserCore | None,
    password_hash: str | None,
    refresh_repo: _StubRefreshRepo,
    issued: dict[UUID, str] | None = None,
) -> LoginService:
    return LoginService(
        users=_StubUserRepo(user),  # type: ignore[arg-type]
        credentials=_StubCredsRepo(password_hash),  # type: ignore[arg-type]
        refresh_tokens=refresh_repo,  # type: ignore[arg-type]
        registration_numbers=_StubRegistrationRepo(issued),  # type: ignore[arg-type]
        jwt=_jwt(),
    )


@pytest.mark.asyncio
async def test_login_success_issues_and_persists_tokens() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, hash_password("SecurePass123!"), refresh_repo)

    result = await service.login(identifier="buyer@example.com", password="SecurePass123!")

    assert result.user_id == user.id
    assert result.role == "buyer"
    assert result.tokens.access_token
    assert len(refresh_repo.created) == 1


@pytest.mark.asyncio
async def test_unknown_email_is_invalid() -> None:
    refresh_repo = _StubRefreshRepo()
    service = _service(None, None, refresh_repo)
    with pytest.raises(InvalidCredentials):
        await service.login(identifier="nobody@example.com", password="whatever12")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_no_password_set_is_invalid() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, None, refresh_repo)  # user exists, no credential
    with pytest.raises(InvalidCredentials):
        await service.login(identifier="buyer@example.com", password="whatever12")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_wrong_password_is_invalid() -> None:
    user = UserCore(id=uuid4(), role="buyer", verified_status="phone_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(user, hash_password("CorrectPass1!"), refresh_repo)
    with pytest.raises(InvalidCredentials):
        await service.login(identifier="buyer@example.com", password="WrongPass1!")
    assert refresh_repo.created == []


# --- registration-number identifier (SCRUM-207) -----------------------------


@pytest.mark.asyncio
async def test_approved_realtor_signs_in_with_registration_number() -> None:
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(
        realtor,
        hash_password("SecurePass123!"),
        refresh_repo,
        issued={realtor.id: "MH-R-000123"},
    )

    result = await service.login(identifier="MH-R-000123", password="SecurePass123!")

    assert result.user_id == realtor.id
    assert result.role == "realtor"


@pytest.mark.asyncio
async def test_registration_number_is_case_and_space_insensitive() -> None:
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(
        realtor,
        hash_password("SecurePass123!"),
        refresh_repo,
        issued={realtor.id: "MH-R-000123"},
    )

    result = await service.login(identifier=" mh-r-000 123 ", password="SecurePass123!")

    assert result.user_id == realtor.id


@pytest.mark.asyncio
async def test_approved_realtor_cannot_sign_in_with_email() -> None:
    """The whole point of SCRUM-207: once the number exists, it is the only way
    in for that realtor — and the refusal is indistinguishable from a wrong
    password, so it cannot be used to discover who is an approved realtor."""
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(
        realtor,
        hash_password("SecurePass123!"),
        refresh_repo,
        issued={realtor.id: "MH-R-000123"},
    )

    with pytest.raises(InvalidCredentials):
        await service.login(identifier="realtor@example.com", password="SecurePass123!")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_realtor_without_a_number_still_signs_in_with_email() -> None:
    """A pending or rejected application has no number yet. Refusing email here
    would lock the realtor out of the screen that tells them so, and out of
    re-submitting after a rejection."""
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(realtor, hash_password("SecurePass123!"), refresh_repo, issued={})

    result = await service.login(identifier="realtor@example.com", password="SecurePass123!")

    assert result.user_id == realtor.id


@pytest.mark.asyncio
async def test_unknown_registration_number_is_invalid() -> None:
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(
        realtor, hash_password("SecurePass123!"), refresh_repo, issued={realtor.id: "MH-R-000123"}
    )
    with pytest.raises(InvalidCredentials):
        await service.login(identifier="MH-R-999999", password="SecurePass123!")
    assert refresh_repo.created == []


@pytest.mark.asyncio
async def test_malformed_identifier_is_invalid_not_an_error() -> None:
    """Neither an email nor a well-formed number. It must fail like any other
    bad credential — a 422 would tell the client its guess had the wrong shape."""
    realtor = UserCore(id=uuid4(), role="realtor", verified_status="id_verified")
    refresh_repo = _StubRefreshRepo()
    service = _service(realtor, hash_password("SecurePass123!"), refresh_repo)
    with pytest.raises(InvalidCredentials):
        await service.login(identifier="not-a-number", password="SecurePass123!")
