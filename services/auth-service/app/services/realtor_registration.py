"""Issue a realtor's Maihomme registration number (SCRUM-207).

Called by realtor-service over POST /internal/realtors/{user_id}/registration-number
at the moment an admin approves a realtor application. auth-service owns the
number because LOGIN has to resolve it, and login is not realtor-service's to
serve (CLAUDE.md §3).

Two invariants this service exists to hold:

  1. **Realtors only.** A number authenticates its holder, and only the realtor
     surface is meant to be reached this way. Minting one for a buyer would
     hand that account a second login identifier nobody asked for, so the role
     is checked here rather than trusted from the caller.

  2. **At most one live number per realtor, ever.** Issuance is idempotent: a
     retried approval returns the number already issued. Two numbers would both
     authenticate, and only one of them was ever emailed.

Non-§11: no financial record, no schema change at call time, and no §11 table
is touched — the number lives in its own table (migration 0015).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.realtor_registration_repo import RealtorRegistrationRepository
from app.repositories.user_repo import UserRepository
from app.security import CurrentUser

logger = logging.getLogger(__name__)


class RegistrationNumberError(RuntimeError):
    pass


class RealtorNotFound(RegistrationNumberError):
    """No live account with that id."""


class NotRealtorRole(RegistrationNumberError):
    """The account exists but is not a realtor."""


@dataclass(frozen=True)
class RegistrationNumberResult:
    user_id: UUID
    registration_number: str
    newly_issued: bool


class RealtorRegistrationService:
    def __init__(
        self,
        *,
        users: UserRepository,
        numbers: RealtorRegistrationRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._users = users
        self._numbers = numbers
        self._audit = audit

    async def issue(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RegistrationNumberResult:
        user = await self._users.get_active_by_id(user_id)
        if user is None:
            raise RealtorNotFound()
        if user.role != "realtor":
            raise NotRealtorRole()

        issued = await self._numbers.issue(user_id)

        # Only the first issuance is a state change worth recording. Auditing a
        # no-op retry would fill the trail with rows that describe nothing.
        if issued.newly_issued:
            await self._audit.record(
                actor_id=actor.user_id,
                actor_role=actor.role,
                action="realtor.registration_number_issued",
                entity_type="user",
                entity_id=user_id,
                new_value={"registration_number": issued.registration_number},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            logger.info(
                "realtor.registration_number.issued",
                extra={"user_id": str(user_id)},
            )

        return RegistrationNumberResult(
            user_id=user_id,
            registration_number=issued.registration_number,
            newly_issued=issued.newly_issued,
        )
