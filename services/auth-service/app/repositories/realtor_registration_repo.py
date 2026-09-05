"""DB access for realtor_registration_numbers (SCRUM-207).

Repository layer per CLAUDE.md §4 — the issuance service and the login service
call these, never the ORM directly.

Every read filters `deleted_at IS NULL`: a revoked number must stop
authenticating immediately, and must not block a fresh one being issued to the
same realtor.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RealtorRegistrationNumber
from app.services.registration_number import PREFIX


class RegistrationNumberNotIssued(RuntimeError):
    """The INSERT was skipped by ON CONFLICT and the row could not then be read
    back. Only reachable if the row was revoked between the two statements —
    the caller turns it into a retryable failure rather than guessing."""


@dataclass(frozen=True)
class IssuedNumber:
    registration_number: str
    # False when the realtor already had one — issuance is idempotent, so a
    # retried approval returns the existing number rather than minting a second.
    newly_issued: bool


class RealtorRegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: UUID) -> str | None:
        """The realtor's live registration number, or None if none was issued."""
        stmt = select(RealtorRegistrationNumber.registration_number).where(
            RealtorRegistrationNumber.user_id == user_id,
            RealtorRegistrationNumber.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_user_id(self, registration_number: str) -> UUID | None:
        """The realtor a registration number belongs to — the login lookup."""
        stmt = select(RealtorRegistrationNumber.user_id).where(
            RealtorRegistrationNumber.registration_number == registration_number,
            RealtorRegistrationNumber.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def issue(self, user_id: UUID) -> IssuedNumber:
        """Issue this realtor's number, or return the one they already have.

        The value comes from `nextval` INSIDE the INSERT, so no two callers can
        pick the same one and no retry loop is needed.

        Idempotent by design — an admin whose approval half-failed will retry,
        and a realtor must never end up with two numbers (the second would
        authenticate just as well as the first, and the email only carried one).
        The partial unique index makes ON CONFLICT the arbiter rather than the
        read below, which closes the window between checking and inserting.
        """
        existing = await self.get_for_user(user_id)
        if existing is not None:
            return IssuedNumber(registration_number=existing, newly_issued=False)

        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO realtor_registration_numbers (user_id, registration_number)
                    VALUES (
                        :user_id,
                        :prefix || LPAD(nextval('realtor_registration_number_seq')::text, 6, '0')
                    )
                    ON CONFLICT (user_id) WHERE deleted_at IS NULL DO NOTHING
                    RETURNING registration_number
                    """
                ),
                {"user_id": user_id, "prefix": PREFIX},
            )
        ).first()
        if row is not None:
            await self._session.flush()
            return IssuedNumber(registration_number=row.registration_number, newly_issued=True)

        # Lost the race to a concurrent issuance. That transaction has committed
        # by the time our blocked INSERT returned, so this read sees its row.
        concurrent = await self.get_for_user(user_id)
        if concurrent is None:
            raise RegistrationNumberNotIssued()
        return IssuedNumber(registration_number=concurrent, newly_issued=False)
