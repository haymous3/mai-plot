"""Set the caller's personal details after phone-OTP verification (SCRUM-132).

The onboarding wizard's "Personal details" screen collects a full name
(required) and an optional email once the user is OTP-verified. This writes
them to the caller's own rows via UserRepository — full_name to user_pii, email
to users. Non-§11: a user's self-service profile edit, not a schema migration or
a financial override. Email is unique, so a collision with another account maps
to a clean 409 rather than a 500 (pre-check mirrors the phone/BVN convention).
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.user_repo import UserRepository


class InvalidFullName(RuntimeError):
    """full_name is blank once surrounding whitespace is stripped."""


class EmailAlreadyInUse(RuntimeError):
    """The email belongs to a different live account."""


class ProfileService:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    async def update(self, *, user_id: UUID, full_name: str, email: str | None) -> None:
        name = full_name.strip()
        if not name:
            raise InvalidFullName
        normalised_email = email.strip().lower() if email and email.strip() else None
        if normalised_email is not None and await self._users.email_taken_by_other(
            normalised_email, user_id=user_id
        ):
            raise EmailAlreadyInUse
        await self._users.update_profile(user_id, full_name=name, email=normalised_email)
