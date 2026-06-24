"""Admin access to a realtor's uploaded government-ID document (SCRUM-62).

The ID document lives in the PRIVATE documents bucket and is never public
(CLAUDE.md). When an admin reviews an application they get a short-TTL pre-signed
GET URL — minted here, the access recorded in audit_log. The document bytes never
pass through this service (only the object key + signed URL).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.document_storage import DocumentStorage
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.realtor_repo import RealtorRepository
from app.security import CurrentUser
from app.services.realtor_review import RealtorNotFound


class CredentialUnavailable(RuntimeError):
    """The realtor has no government-ID document on file."""


@dataclass(frozen=True)
class CredentialAccessService:
    realtors: RealtorRepository
    audit: AuditLogRepository
    storage: DocumentStorage
    presign_ttl_seconds: int

    async def government_id_url(
        self,
        *,
        user_id: UUID,
        viewer: CurrentUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """A pre-signed GET URL for the realtor's ID document. Raises
        RealtorNotFound if there's no such realtor, CredentialUnavailable if they
        never uploaded one. Records the access in audit_log."""
        realtor = await self.realtors.get(user_id)
        if realtor is None:
            raise RealtorNotFound()
        if not realtor.government_id_s3_key:
            raise CredentialUnavailable()

        url = self.storage.presigned_get_url(
            realtor.government_id_s3_key, expires_seconds=self.presign_ttl_seconds
        )
        await self.audit.record(
            actor_id=viewer.user_id,
            actor_role=viewer.role,
            action="realtor.credential_viewed",
            entity_type="realtor",
            entity_id=user_id,
            new_value={"document": "government_id"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return url
