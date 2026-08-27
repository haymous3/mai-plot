"""Unit tests for ChangePasswordService (SCRUM-188).

Stubbed repositories — the point here is the DECISION logic, especially the
order of the checks, which is what carries the security properties.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

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


def _service(
    stored: str | None,
) -> tuple[ChangePasswordService, _StubCredentials, _StubRefreshTokens]:
    creds = _StubCredentials(stored)
    tokens = _StubRefreshTokens()
    service = ChangePasswordService(
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
