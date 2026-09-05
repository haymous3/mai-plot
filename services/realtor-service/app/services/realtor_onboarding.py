"""Realtor onboarding (SCRUM-71).

A user registered as a realtor completes their profile: coverage areas, years of
experience, and a government-ID upload (private S3). The profile lands at
approval_status='pending' for legal/admin review. A realtor who was previously
rejected may re-submit; an already-pending/approved/suspended realtor cannot
re-register (409).

⚠️ NO ESVARBON LICENCE (SCRUM-207). It used to be collected and format-validated
here; the product now verifies a realtor through admin review and issues them a
Maihomme registration number at approval instead. `realtors.esvarbon_number`
stays nullable and keeps the values realtors supplied before — this writes NULL
into it rather than dropping the column, so no historic licence is destroyed.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.realtor_repo import RealtorRepository, RealtorRow
from app.services.credentials import (
    InvalidCredential,
    build_id_object_key,
    detect_id_document_type,
    validate_coordinates,
    validate_id_size,
)

logger = logging.getLogger(__name__)

_RESUBMITTABLE_STATUS = "rejected"


class RealtorOnboardingError(RuntimeError):
    pass


class NotRealtorRole(RealtorOnboardingError):
    """Caller's role is not 'realtor'."""


class AlreadyRegistered(RealtorOnboardingError):
    """A non-rejected realtor profile already exists for this user."""


class StorageUnavailable(RealtorOnboardingError):
    """The ID document storage backend failed — retryable."""


class RealtorOnboardingService:
    def __init__(
        self,
        *,
        realtors: RealtorRepository,
        audit: AuditLogRepository,
        storage: DocumentStorage,
        max_upload_bytes: int,
    ) -> None:
        self._realtors = realtors
        self._audit = audit
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    async def register(
        self,
        *,
        user_id: UUID,
        role: str,
        years_of_experience: int | None,
        coverage_states: list[str],
        coverage_lgas: list[str],
        id_document: bytes,
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

        # Validate the credentials (InvalidCredential -> 422). Coverage must name
        # at least one state — a realtor has to cover somewhere.
        if not coverage_states:
            raise InvalidCredential("COVERAGE_REQUIRED", "At least one coverage state is required.")
        has_location = base_lat is not None and base_lng is not None
        if has_location:
            validate_coordinates(base_lat, base_lng)  # type: ignore[arg-type]
        validate_id_size(id_document, max_bytes=self._max_upload_bytes)
        content_type, extension = detect_id_document_type(id_document)

        key = build_id_object_key(user_id, extension=extension)
        try:
            stored = await self._storage.put(key=key, data=id_document, content_type=content_type)
        except DocumentStorageError as exc:
            logger.error("realtor.register.storage_unavailable", extra={"user_id": str(user_id)})
            raise StorageUnavailable() from exc

        if existing is None:
            realtor = await self._realtors.create(
                user_id=user_id,
                years_of_experience=years_of_experience,
                coverage_states=coverage_states,
                coverage_lgas=coverage_lgas,
                government_id_s3_key=key,
            )
        else:  # re-submit after a rejection
            realtor = await self._realtors.resubmit(
                user_id=user_id,
                years_of_experience=years_of_experience,
                coverage_states=coverage_states,
                coverage_lgas=coverage_lgas,
                government_id_s3_key=key,
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
                "id_s3_key": key,
                "content_type": stored.content_type,
                "size": stored.size,
                "resubmit": existing is not None,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("realtor.register.ok", extra={"user_id": str(user_id)})
        return realtor
