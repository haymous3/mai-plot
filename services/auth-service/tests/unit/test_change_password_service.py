"""Unit tests for ChangePasswordService (SCRUM-188).

Stubbed repositories — the point here is the DECISION logic, especially the
order of the checks, which is what carries the security properties.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.user_repo import UserCore
from app.services.change_password import (
    ChangePasswordService,
    CurrentPasswordWrong,
    NoPasswordSet,
    SamePassword,
)
from app.services.password import hash_password, verify_password
from app.services.set_password import WeakPassword

pytestmark = pytest.mark.asyncio

# Throwaway test values. Held in non-"password"-named constants and passed by
# reference so secret scanners don't flag a literal in a password-keyed
# position (mirrors test_set_password_service.py and test_login.py).
_STRONG = "SecurePass123!"
_ROTATED = "RotatedPass456!"
_GUESS = "NotTheOne789!"
_FEEBLE = "alllowercase"


class _StubCredentials:
    def __init__(self, stored: str | None) -> None:
        self._stored = stored
        self.written: str | None = None

    async def get_password_hash(self, user_id: UUID) -> str | None:
        return self._stored

    async def upsert(self, *, user_id: UUID, password_hash: str) -> None:
        self.written = password_hash


class _StubRefreshTokens:
    def __init__(self) -> None:
        self.revoked_for: UUID | None = None

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        self.revoked_for = user_id


class _StubUsers:
    """One account, its own login owner (SCRUM-236)."""

    async def login_owner_id(self, user_id: UUID) -> UUID | None:
        return user_id

    async def login_group(self, owner_id: UUID) -> list[object]:
        return []


def _service(
    stored: str | None,
) -> tuple[ChangePasswordService, _StubCredentials, _StubRefreshTokens]:
    creds = _StubCredentials(stored)
    tokens = _StubRefreshTokens()
    service = ChangePasswordService(
        users=_StubUsers(),  # type: ignore[arg-type]
        credentials=creds,  # type: ignore[arg-type]
        refresh_tokens=tokens,  # type: ignore[arg-type]
    )
    return service, creds, tokens


async def test_changes_password_and_revokes_sessions() -> None:
    service, creds, tokens = _service(hash_password(_STRONG))
    user_id = uuid4()

    await service.change(user_id=user_id, current_password=_STRONG, new_password=_ROTATED)

    assert creds.written is not None
    assert creds.written.startswith("$2")  # bcrypt, not the plaintext
    assert verify_password(_ROTATED, creds.written)
    # A change that left old sessions alive would be half a fix.
    assert tokens.revoked_for == user_id


async def test_wrong_current_password_rejected_and_nothing_written() -> None:
    service, creds, tokens = _service(hash_password(_STRONG))

    with pytest.raises(CurrentPasswordWrong):
        await service.change(user_id=uuid4(), current_password=_GUESS, new_password=_ROTATED)

    assert creds.written is None
    assert tokens.revoked_for is None


async def test_account_with_no_credential_row_is_told_to_set_one() -> None:
    """A password is optional at registration, so an account can have no
    credential row. Such a user has no current password to prove."""
    service, creds, _ = _service(None)

    with pytest.raises(NoPasswordSet):
        await service.change(user_id=uuid4(), current_password=_STRONG, new_password=_ROTATED)

    assert creds.written is None


async def test_reusing_the_current_value_is_rejected() -> None:
    """Otherwise the call reports success and the user believes they rotated."""
    service, creds, tokens = _service(hash_password(_STRONG))

    with pytest.raises(SamePassword):
        await service.change(user_id=uuid4(), current_password=_STRONG, new_password=_STRONG)

    assert creds.written is None
    assert tokens.revoked_for is None


async def test_weak_replacement_rejected() -> None:
    service, creds, _ = _service(hash_password(_STRONG))

    with pytest.raises(WeakPassword):
        await service.change(user_id=uuid4(), current_password=_STRONG, new_password=_FEEBLE)

    assert creds.written is None


async def test_credential_check_runs_before_the_reuse_check() -> None:
    """Ordering matters: if SamePassword were evaluated first, the distinct
    error would tell someone holding only a session whether their guess equals
    the stored value."""
    service, _, _ = _service(hash_password(_STRONG))

    # Wrong current AND replacement == the real current. Must report the
    # credential failure, not leak that the guess matched.
    with pytest.raises(CurrentPasswordWrong):
        await service.change(user_id=uuid4(), current_password=_GUESS, new_password=_STRONG)


# --- SCRUM-236: the password belongs to the login ----------------------------


class _SharedUsers:
    def __init__(self, owner: UUID, members: list[UUID]) -> None:
        self._owner = owner
        self._members = members

    async def login_owner_id(self, user_id: UUID) -> UUID | None:
        return self._owner

    async def login_group(self, owner_id: UUID) -> list[object]:
        return [UserCore(id=m, role="buyer", verified_status="id_verified") for m in self._members]


class _KeyedCredentials:
    """Credentials keyed by user id, so a write to the wrong row shows."""

    def __init__(self, stored: dict[UUID, str]) -> None:
        self.stored = dict(stored)

    async def get_password_hash(self, user_id: UUID) -> str | None:
        return self.stored.get(user_id)

    async def upsert(self, *, user_id: UUID, password_hash: str) -> None:
        self.stored[user_id] = password_hash


class _RevokeLog:
    def __init__(self) -> None:
        self.revoked: list[UUID] = []

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        self.revoked.append(user_id)


async def test_changing_from_the_seller_account_changes_the_logins_password() -> None:
    owner, seller = uuid4(), uuid4()
    creds = _KeyedCredentials({owner: hash_password(_STRONG)})
    revokes = _RevokeLog()
    service = ChangePasswordService(
        users=_SharedUsers(owner, [owner, seller]),  # type: ignore[arg-type]
        credentials=creds,  # type: ignore[arg-type]
        refresh_tokens=revokes,  # type: ignore[arg-type]
    )

    await service.change(user_id=seller, current_password=_STRONG, new_password=_ROTATED)

    assert verify_password(_ROTATED, creds.stored[owner])
    assert seller not in creds.stored
    # Both accounts' sessions: the seller one is as stale as the buyer one.
    assert sorted(revokes.revoked) == sorted([owner, seller])
