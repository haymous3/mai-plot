"""Profile-photo upload / removal orchestration (SCRUM-188).

Mirrors `poa_upload.py`: the bytes go to the PRIVATE documents bucket and only
the S3 key is persisted. The image never reaches a log, a broker or the
database.

Unlike PoA there is no eligibility gate — every role may set a photo — and no
"already submitted" conflict, because replacing your own picture is the normal
case rather than a re-submission after rejection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.user_repo import UserRepository
from app.services.avatar import build_object_key, detect_image_type, validate_size

logger = logging.getLogger(__name__)


class AvatarError(RuntimeError):
    pass


class AvatarStorageUnavailable(AvatarError):
    """The storage backend failed — a retryable condition."""


class AvatarUserMissing(AvatarError):
    """No live account for this id (deleted or deactivated mid-request)."""


@dataclass(frozen=True)
class AvatarUploadResult:
    s3_key: str
    url: str


class AvatarService:
    def __init__(
        self,
        *,
        users: UserRepository,
        storage: DocumentStorage,
        max_upload_bytes: int,
        url_ttl_seconds: int,
    ) -> None:
        self._users = users
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes
        self._url_ttl_seconds = url_ttl_seconds

    def presigned_url(self, key: str | None) -> str | None:
        """Mint a short-lived read URL for a stored key, or None if unset.

        The bucket is private (§4), so this is the only way a browser can
        fetch the image. TTL is the same 15 minutes the document path uses.
        """
        if key is None:
            return None
        return self._storage.presigned_get_url(key, expires_seconds=self._url_ttl_seconds)

    async def upload(self, *, user_id: UUID, data: bytes) -> AvatarUploadResult:
        """Validate, store, and point the account at the new object.

        Order matters. The bytes are validated BEFORE anything is written, and
        the DB row is repointed BEFORE the previous object is deleted — so a
        failure at the delete step leaves an orphaned object rather than a row
        pointing at a key that no longer exists. An orphan costs storage; a
        dangling key shows the user a broken image.
        """
        validate_size(data, max_bytes=self._max_upload_bytes)
        content_type, extension = detect_image_type(data)

        key = build_object_key(user_id, extension=extension)
        try:
            await self._storage.put(key=key, data=data, content_type=content_type)
        except DocumentStorageError as exc:
            # Never echo the exception's payload — keep the failure generic.
            logger.warning("avatar upload failed for user %s: %s", user_id, type(exc).__name__)
            raise AvatarStorageUnavailable() from exc

        found, previous = await self._users.set_avatar_key(user_id, key=key)
        if not found:
            # The account vanished between authentication and this write. The
            # object we just stored now belongs to nobody, so remove it rather
            # than leaving an unreferenced image in the bucket.
            await self._discard(key, user_id=user_id)
            raise AvatarUserMissing()

        await self._discard(previous, user_id=user_id)
        url = self._storage.presigned_get_url(key, expires_seconds=self._url_ttl_seconds)
        return AvatarUploadResult(s3_key=key, url=url)

    async def remove(self, *, user_id: UUID) -> None:
        """Clear the photo and delete the object. Idempotent: removing a photo
        that is not there is success, not a 404 — the caller's intent ("I want
        no photo") is already satisfied."""
        _found, previous = await self._users.set_avatar_key(user_id, key=None)
        await self._discard(previous, user_id=user_id)

    async def _discard(self, key: str | None, *, user_id: UUID) -> None:
        """Best-effort delete of a superseded object.

        Deliberately swallows storage errors. The row already no longer points
        at this key, so the user-visible outcome is correct either way; failing
        the whole request over an orphaned object would turn a successful
        upload into an error. The orphan is logged so a lifecycle sweep can
        collect it.
        """
        if key is None:
            return
        try:
            await self._storage.delete(key)
        except DocumentStorageError:
            logger.warning("orphaned avatar object for user %s: %s", user_id, key)
