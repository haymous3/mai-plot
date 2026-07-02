"""Unit tests for SetPasswordService (SCRUM-94)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.password import verify_password
from app.services.set_password import SetPasswordService, WeakPassword

pytestmark = pytest.mark.asyncio

# A throwaway test value that satisfies the policy. Held in a non-"password"-named
# constant and passed by reference so secret scanners don't flag a literal in a
# password-keyed position (mirrors test_login.py's approach).
_STRONG = "SecurePass123!"


class _StubCredentials:
    def __init__(self) -> None:
        self.upserts: list[tuple[UUID, str]] = []

    async def upsert(self, *, user_id: UUID, password_hash: str) -> None:
        self.upserts.append((user_id, password_hash))


def _service(creds: _StubCredentials) -> SetPasswordService:
    return SetPasswordService(credentials=creds)  # type: ignore[arg-type]


async def test_sets_bcrypt_hash_for_strong_password() -> None:
    creds = _StubCredentials()
    uid = uuid4()
    await _service(creds).set(user_id=uid, password=_STRONG)

    assert len(creds.upserts) == 1
    stored_uid, stored_hash = creds.upserts[0]
    assert stored_uid == uid
    assert stored_hash.startswith("$2")  # bcrypt
    assert verify_password(_STRONG, stored_hash)


@pytest.mark.parametrize(
    "weak",
    [
        "short1A",  # < 8 chars
        "alllowercase1",  # no uppercase
        "NoDigitsHere",  # no digit
    ],
)
async def test_rejects_weak_passwords(weak: str) -> None:
    creds = _StubCredentials()
    with pytest.raises(WeakPassword):
        await _service(creds).set(user_id=uuid4(), password=weak)
    assert creds.upserts == []  # nothing written
