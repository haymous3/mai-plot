"""Unit tests for ProfileService (SCRUM-132)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.profile import EmailAlreadyInUse, InvalidFullName, ProfileService

pytestmark = pytest.mark.asyncio


class _StubUsers:
    def __init__(self, *, taken: bool = False) -> None:
        self._taken = taken
        self.updates: list[dict[str, object]] = []
        self.checked: list[str] = []

    async def email_taken_by_other(self, email: str, *, user_id: UUID) -> bool:
        self.checked.append(email)
        return self._taken

    async def update_profile(self, user_id: UUID, *, full_name: str, email: str | None) -> None:
        self.updates.append({"user_id": user_id, "full_name": full_name, "email": email})


def _service(users: _StubUsers) -> ProfileService:
    return ProfileService(users=users)  # type: ignore[arg-type]


async def test_saves_trimmed_name_and_normalised_email() -> None:
    users = _StubUsers()
    uid = uuid4()
    await _service(users).update(user_id=uid, full_name="  Ada Obi  ", email="  Ada@Mai.NG ")

    assert users.updates == [{"user_id": uid, "full_name": "Ada Obi", "email": "ada@mai.ng"}]
    assert users.checked == ["ada@mai.ng"]  # uniqueness checked with the normalised value


async def test_email_optional_is_left_as_none() -> None:
    users = _StubUsers()
    await _service(users).update(user_id=uuid4(), full_name="Ada", email=None)

    assert users.updates[0]["email"] is None
    assert users.checked == []  # no uniqueness check when no email supplied


async def test_blank_email_string_treated_as_none() -> None:
    users = _StubUsers()
    await _service(users).update(user_id=uuid4(), full_name="Ada", email="   ")

    assert users.updates[0]["email"] is None
    assert users.checked == []


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
async def test_blank_full_name_rejected(name: str) -> None:
    users = _StubUsers()
    with pytest.raises(InvalidFullName):
        await _service(users).update(user_id=uuid4(), full_name=name, email=None)
    assert users.updates == []  # nothing written


async def test_email_taken_by_other_rejected() -> None:
    users = _StubUsers(taken=True)
    with pytest.raises(EmailAlreadyInUse):
        await _service(users).update(user_id=uuid4(), full_name="Ada", email="dup@mai.ng")
    assert users.updates == []  # not persisted when the email collides
