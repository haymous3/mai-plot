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

    async def update_profile(
        self,
        user_id: UUID,
        *,
        full_name: str,
        email: str | None,
        location: str | None = None,
        set_location: bool = False,
        address: str | None = None,
        set_address: bool = False,
    ) -> None:
        self.updates.append(
            {
                "user_id": user_id,
                "full_name": full_name,
                "email": email,
                "location": location,
                "set_location": set_location,
                "address": address,
                "set_address": set_address,
            }
        )


def _service(users: _StubUsers) -> ProfileService:
    return ProfileService(users=users)  # type: ignore[arg-type]


async def test_saves_trimmed_name_and_normalised_email() -> None:
    users = _StubUsers()
    uid = uuid4()
    await _service(users).update(user_id=uid, full_name="  Ada Obi  ", email="  Ada@Mai.NG ")

    assert users.updates == [
        {
            "user_id": uid,
            "full_name": "Ada Obi",
            "email": "ada@mai.ng",
            # Not sent by this caller, so the stored location is left alone.
            "location": None,
            "set_location": False,
            "address": None,
            "set_address": False,
        }
    ]
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


# --------------------------------------------------------------------------
# SCRUM-193 — location is tri-state, unlike email
# --------------------------------------------------------------------------


async def test_location_is_not_written_when_the_caller_omits_it() -> None:
    """An edit that only changes the name must not wipe a stored location."""
    users = _StubUsers()
    await _service(users).update(user_id=uuid4(), full_name="Ada", email=None)

    assert users.updates[0]["set_location"] is False


async def test_location_is_trimmed_and_passed_through() -> None:
    users = _StubUsers()
    await _service(users).update(
        user_id=uuid4(), full_name="Ada", email=None, location="  Lagos  ", set_location=True
    )

    assert users.updates[0]["location"] == "Lagos"
    assert users.updates[0]["set_location"] is True


async def test_blank_location_becomes_none_so_it_clears() -> None:
    """ "Said nothing" is stored the same way as "not said" — never as ""."""
    users = _StubUsers()
    await _service(users).update(
        user_id=uuid4(), full_name="Ada", email=None, location="   ", set_location=True
    )

    assert users.updates[0]["location"] is None
    # Still an explicit write: the caller asked to end up with no location.
    assert users.updates[0]["set_location"] is True


async def test_address_is_trimmed_and_passed_through() -> None:
    users = _StubUsers()
    await _service(users).update(
        user_id=uuid4(),
        full_name="Ada",
        email=None,
        address="  12 Admiralty Way  ",
        set_address=True,
    )

    assert users.updates[0]["address"] == "12 Admiralty Way"
    assert users.updates[0]["set_address"] is True


async def test_address_is_not_written_when_omitted() -> None:
    """Editing only a name must not wipe a stored address."""
    users = _StubUsers()
    await _service(users).update(user_id=uuid4(), full_name="Ada", email=None)

    assert users.updates[0]["set_address"] is False


async def test_blank_address_becomes_none_so_it_clears() -> None:
    users = _StubUsers()
    await _service(users).update(
        user_id=uuid4(), full_name="Ada", email=None, address="   ", set_address=True
    )

    assert users.updates[0]["address"] is None
    assert users.updates[0]["set_address"] is True
