"""Realtor onboarding (SCRUM-71).

A user registered as a realtor completes their profile: coverage areas and years
of experience. The profile lands at approval_status='pending' for legal/admin
review. A realtor who was previously rejected may re-submit; an
already-pending/approved/suspended realtor cannot re-register (409).

⚠️ NO ESVARBON LICENCE (SCRUM-207). It used to be collected and format-validated
here; the product now verifies a realtor through admin review and issues them a
Maihomme registration number at approval instead. `realtors.esvarbon_number`
stays nullable and keeps the values realtors supplied before — this writes NULL
into it rather than dropping the column, so no historic licence is destroyed.

⚠️ NO GOVERNMENT-ID DOCUMENT (SCRUM-219). The upload the onboarding screen
called "Professional Credentials" is no longer collected, so this service never
touches object storage: no sniffing, no size check, no S3 put, and no
StorageUnavailable. `realtors.government_id_s3_key` is treated the same way as
esvarbon_number — left alone on both create and re-submit, so the documents
already uploaded keep their keys and no S3 object is orphaned by a re-apply.
The admin review that used to read those documents is gone too, so nothing in
the product resolves a key any more.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.realtor_repo import RealtorRepository, RealtorRow
from app.services.credentials import InvalidCredential, validate_base_location

logger = logging.getLogger(__name__)

_RESUBMITTABLE_STATUS = "rejected"


class RealtorOnboardingError(RuntimeError):
    pass


class NotRealtorRole(RealtorOnboardingError):
    """Caller's role is not 'realtor'."""


class AlreadyRegistered(RealtorOnboardingError):
    """A non-rejected realtor profile already exists for this user."""


class RealtorNotFound(RealtorOnboardingError):
    """No realtor profile for this account yet — onboard first."""


class RealtorOnboardingService:
    def __init__(
        self,
        *,
        realtors: RealtorRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._realtors = realtors
        self._audit = audit

    async def register(
        self,
        *,
        user_id: UUID,
        role: str,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        base_lat: float | None = None,
        base_lng: float | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RealtorRow:
        if role != "realtor":
            raise NotRealtorRole()

        existing = await self._realtors.get(user_id)
        if existing is not None and existing.approval_status != _RESUBMITTABLE_STATUS:
            raise AlreadyRegistered()

        # Validate what is left (InvalidCredential -> 422). Coverage must name
        # at least one state — a realtor has to cover somewhere.
        if not coverage_states:
            raise InvalidCredential("COVERAGE_REQUIRED", "At least one coverage state is required.")
        has_location = base_lat is not None and base_lng is not None
        if has_location:
            validate_base_location(base_lat, base_lng)  # type: ignore[arg-type]

        if existing is None:
            realtor = await self._realtors.create(
                user_id=user_id,
                years_of_experience=years_of_experience,
                coverage_states=coverage_states,
                coverage_lgas=coverage_lgas,
            )
        else:  # re-submit after a rejection
            realtor = await self._realtors.resubmit(
                user_id=user_id,
                years_of_experience=years_of_experience,
                coverage_states=coverage_states,
                coverage_lgas=coverage_lgas,
            )

        if has_location:
            await self._realtors.set_base_location(user_id, lat=base_lat, lng=base_lng)  # type: ignore[arg-type]

        await self._audit.record(
            actor_id=user_id,
            actor_role=role,
            action="realtor.registered",
            entity_type="realtor",
            entity_id=user_id,
            new_value={
                "approval_status": "pending",
                "coverage_states": coverage_states,
                "resubmit": existing is not None,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("realtor.register.ok", extra={"user_id": str(user_id)})
        return realtor

    async def set_base_location(
        self,
        *,
        user_id: UUID,
        role: str,
        lat: float,
        lng: float,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RealtorRow:
        """Set or move the realtor's base (SCRUM-214) — what proximity assignment
        and reassignment search from. Any approval status may set it: a pending
        realtor who sets it now is assignable the moment they are approved.

        Audited with coordinates rounded to ~1 km (3 dp): enough to explain a
        change of assignments, without the trail pinpointing someone's home.
        """
        if role != "realtor":
            raise NotRealtorRole()
        existing = await self._realtors.get(user_id)
        if existing is None:
            raise RealtorNotFound()
        validate_base_location(lat, lng)

        await self._realtors.set_base_location(user_id, lat=lat, lng=lng)
        await self._audit.record(
            actor_id=user_id,
            actor_role=role,
            action="realtor.base_location_set",
            entity_type="realtor",
            entity_id=user_id,
            old_value=_rounded(existing.base_lat, existing.base_lng),
            new_value=_rounded(lat, lng),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        updated = await self._realtors.get(user_id)
        assert updated is not None  # the row existed a moment ago, in this transaction
        logger.info(
            "realtor.base_location_set",
            extra={"user_id": str(user_id), "first": existing.base_lat is None},
        )
        return updated


def _rounded(lat: float | None, lng: float | None) -> dict[str, object] | None:
    if lat is None or lng is None:
        return None
    return {"lat": round(lat, 3), "lng": round(lng, 3)}
