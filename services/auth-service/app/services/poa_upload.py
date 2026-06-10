"""PoA document upload orchestration (SCRUM-48).

Only a seller whose authority_type is `power_of_attorney` may upload a PoA
document. Eligibility is checked from the DB (the JWT carries role but not
seller_authority_type) BEFORE the file is validated, so an ineligible
caller always gets 403 regardless of payload.

On success the document goes to the PRIVATE documents bucket, the user's
poa_verified_status moves to 'pending' (awaiting legal review), and an
append-only audit_log row records the access. The document bytes never
reach a log, a broker, or the database — only the S3 key is persisted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository
from app.services.poa import build_object_key, detect_document_type, validate_size

logger = logging.getLogger(__name__)

# A document already on file blocks a new upload UNLESS it was rejected (the
# seller may re-submit after a rejection). Note we key the conflict off
# has_document, not poa_verified_status: registration pre-sets PoA sellers to
# 'pending' before any upload, so a status check alone would wrongly 409 the
# very first upload.
_REUPLOADABLE_STATUS = "rejected"


class PoaError(RuntimeError):
    pass


class PoaNotEligible(PoaError):
    """Caller is not a seller with authority_type=power_of_attorney."""


class PoaAlreadySubmitted(PoaError):
    """A PoA document is already pending review or verified."""


class PoaStorageUnavailable(PoaError):
    """The storage backend failed — a retryable condition."""


@dataclass(frozen=True)
class PoaUploadResult:
    status: str
    s3_key: str


class PoaUploadService:
    def __init__(
        self,
        *,
        users: UserRepository,
        audit: AuditLogRepository,
        storage: DocumentStorage,
        max_upload_bytes: int,
    ) -> None:
        self._users = users
        self._audit = audit
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    async def upload(
        self,
        *,
        user_id: UUID,
        data: bytes,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PoaUploadResult:
        # Eligibility first — ineligible callers never have their file
        # processed, and always receive 403.
        state = await self._users.get_poa_state(user_id)
        if (
            state is None
            or state.role != "seller"
            or state.seller_authority_type != "power_of_attorney"
        ):
            raise PoaNotEligible()

        if state.has_document and state.poa_verified_status != _REUPLOADABLE_STATUS:
            raise PoaAlreadySubmitted()

        # Validate the bytes server-side (size, then magic-number type).
        # InvalidPoaDocument -> 422; the bytes are never echoed.
        validate_size(data, max_bytes=self._max_upload_bytes)
        content_type, extension = detect_document_type(data)

        key = build_object_key(user_id, extension=extension)
        try:
            stored = await self._storage.put(key=key, data=data, content_type=content_type)
        except DocumentStorageError as exc:
            logger.error("poa.upload.storage_unavailable", extra={"user_id": str(user_id)})
            raise PoaStorageUnavailable() from exc

        await self._users.set_poa_document(user_id, s3_key=key)
        await self._audit.record(
            actor_id=user_id,
            actor_role=state.role,
            action="poa.uploaded",
            entity_type="user",
            entity_id=user_id,
            old_value={"poa_verified_status": state.poa_verified_status},
            new_value={
                "poa_verified_status": "pending",
                "s3_key": key,
                "content_type": stored.content_type,
                "size": stored.size,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("poa.upload.ok", extra={"user_id": str(user_id), "key": key})
        return PoaUploadResult(status="pending", s3_key=key)
