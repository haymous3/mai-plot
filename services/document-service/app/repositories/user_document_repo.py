"""DB access for user_documents (document-service's own table, SCRUM-188).

Personal documents owned by a person rather than scoped to a listing or a loan
— see migration 0003 for why neither existing table could hold them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class UserDocRow:
    id: UUID
    category: str
    file_name: str
    size_bytes: int
    content_type: str
    s3_key: str
    verification_status: str
    verification_notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class UserDocStatus:
    """Owner + status of a personal document, for the admin review path."""

    user_id: UUID
    verification_status: str


@dataclass(frozen=True)
class UserDocQueueRow:
    """One row of the admin review queue.

    `owner_name` is a LEFT JOIN onto user_pii and is None when the owner has
    no name on file — the reviewer then falls back to the user_id.
    """

    id: UUID
    user_id: UUID
    owner_name: str | None
    category: str
    file_name: str
    size_bytes: int
    content_type: str
    verification_status: str
    created_at: datetime


@dataclass(frozen=True)
class CategoryCount:
    category: str
    count: int


@dataclass(frozen=True)
class StatusCount:
    verification_status: str
    count: int


class UserDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_document(
        self,
        *,
        user_id: UUID,
        category: str,
        file_name: str,
        size_bytes: int,
        content_type: str,
        s3_key: str,
    ) -> UUID:
        """Insert a row (verification_status defaults to 'pending') and return its id."""
        document_id = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO user_documents
                        (user_id, category, file_name, size_bytes, content_type, s3_key)
                    VALUES (:uid, :cat, :name, :size, :ctype, :s3)
                    RETURNING id
                    """
                ),
                {
                    "uid": user_id,
                    "cat": category,
                    "name": file_name,
                    "size": size_bytes,
                    "ctype": content_type,
                    "s3": s3_key,
                },
            )
        ).scalar_one()
        assert isinstance(document_id, UUID)
        return document_id

    async def list_for_user(
        self, user_id: UUID, *, category: str | None = None
    ) -> list[UserDocRow]:
        """The caller's live documents, newest first.

        `category` filters to one tab; None is the "All Documents" view. The
        filter is applied in SQL rather than in Python so a user with many
        documents does not pay to transfer the ones they are not looking at.

        ⚠️ `CAST(:cat AS text)`, never `:cat::text`. Postgres's `::` cast
        collides with SQLAlchemy's `:param` syntax and the statement fails to
        parse. Note also that SQLAlchemy scans for `:name` inside SQL COMMENTS
        too, so this explanation lives here rather than beside the clause —
        a comment mentioning a parameter turns into a real bind parameter.
        """
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, category, file_name, size_bytes, content_type,
                           s3_key, verification_status, verification_notes, created_at
                    FROM user_documents
                    WHERE user_id = :uid
                      AND deleted_at IS NULL
                      AND (CAST(:cat AS text) IS NULL OR category = :cat)
                    ORDER BY created_at DESC
                    """
                ),
                {"uid": user_id, "cat": category},
            )
        ).all()
        return [
            UserDocRow(
                id=r.id,
                category=r.category,
                file_name=r.file_name,
                size_bytes=r.size_bytes,
                content_type=r.content_type,
                s3_key=r.s3_key,
                verification_status=r.verification_status,
                verification_notes=r.verification_notes,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def count_by_category(self, user_id: UUID) -> list[CategoryCount]:
        """Per-category totals for the sidebar badges.

        Counted in SQL, not derived from the list above: the list is filtered to
        one category, so counting it would report 0 for every other tab the
        moment a filter is active.
        """
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT category, COUNT(*) AS n
                    FROM user_documents
                    WHERE user_id = :uid AND deleted_at IS NULL
                    GROUP BY category
                    """
                ),
                {"uid": user_id},
            )
        ).all()
        return [CategoryCount(category=r.category, count=int(r.n)) for r in rows]

    async def count_by_status(self, user_id: UUID) -> list[StatusCount]:
        """Per-status totals for the four stat cards."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT verification_status, COUNT(*) AS n
                    FROM user_documents
                    WHERE user_id = :uid AND deleted_at IS NULL
                    GROUP BY verification_status
                    """
                ),
                {"uid": user_id},
            )
        ).all()
        return [
            StatusCount(verification_status=r.verification_status, count=int(r.n)) for r in rows
        ]

    async def get_owned(self, document_id: UUID, *, user_id: UUID) -> UserDocRow | None:
        """One live document, but ONLY if this user owns it.

        Ownership is part of the WHERE clause rather than a check after the
        fetch, so a caller asking for someone else's document id gets the same
        answer as for one that does not exist — no existence oracle.
        """
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id, category, file_name, size_bytes, content_type,
                           s3_key, verification_status, verification_notes, created_at
                    FROM user_documents
                    WHERE id = :id AND user_id = :uid AND deleted_at IS NULL
                    """
                ),
                {"id": document_id, "uid": user_id},
            )
        ).first()
        if row is None:
            return None
        return UserDocRow(
            id=row.id,
            category=row.category,
            file_name=row.file_name,
            size_bytes=row.size_bytes,
            content_type=row.content_type,
            s3_key=row.s3_key,
            verification_status=row.verification_status,
            verification_notes=row.verification_notes,
            created_at=row.created_at,
        )

    async def soft_delete(self, document_id: UUID, *, user_id: UUID) -> bool:
        """Soft-delete one of the caller's documents. True if a row was affected.

        Scoped by user_id in the UPDATE itself for the same reason as
        `get_owned`: a mismatched owner must be indistinguishable from a
        missing row.
        """
        # RETURNING rather than rowcount: SQLAlchemy types execute() as
        # Result[Any], which has no rowcount attribute, and the returned id is
        # a direct answer to "did a row match" anyway.
        updated = (
            await self._session.execute(
                text(
                    """
                    UPDATE user_documents
                    SET deleted_at = NOW(), updated_at = NOW()
                    WHERE id = :id AND user_id = :uid AND deleted_at IS NULL
                    RETURNING id
                    """
                ),
                {"id": document_id, "uid": user_id},
            )
        ).first()
        return updated is not None

    # ------------------------------------------------------------------
    # Admin review (SCRUM-192)
    #
    # The three methods below are the only ones NOT scoped to an owner: a
    # reviewer acts on other people's documents by definition. Every one of
    # them still filters `deleted_at IS NULL` — a document the owner has
    # removed must not surface in a queue or be decidable afterwards.
    # ------------------------------------------------------------------

    async def list_queue(
        self, *, status: str, page: int, page_size: int
    ) -> tuple[list[UserDocQueueRow], int]:
        """Personal documents in a given verification status, oldest-first (FIFO).

        LEFT JOIN so a document whose owner has no `user_pii` row still
        appears — an INNER JOIN would silently drop it from the queue, which
        is the one place a document must never disappear from.
        """
        total = (
            await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM user_documents "
                    "WHERE verification_status = :s AND deleted_at IS NULL"
                ),
                {"s": status},
            )
        ).scalar_one()
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT d.id, d.user_id, p.full_name AS owner_name, d.category,
                           d.file_name, d.size_bytes, d.content_type,
                           d.verification_status, d.created_at
                    FROM user_documents d
                    LEFT JOIN user_pii p ON p.user_id = d.user_id
                    WHERE d.verification_status = :s AND d.deleted_at IS NULL
                    ORDER BY d.created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"s": status, "limit": page_size, "offset": (page - 1) * page_size},
            )
        ).all()
        items = [
            UserDocQueueRow(
                id=r.id,
                user_id=r.user_id,
                owner_name=r.owner_name,
                category=r.category,
                file_name=r.file_name,
                size_bytes=r.size_bytes,
                content_type=r.content_type,
                verification_status=r.verification_status,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, int(total)

    async def get_status(self, document_id: UUID) -> UserDocStatus | None:
        """The owner + current verification status of a personal document, or None."""
        row = (
            await self._session.execute(
                text(
                    "SELECT user_id, verification_status FROM user_documents "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": document_id},
            )
        ).first()
        if row is None:
            return None
        return UserDocStatus(user_id=row.user_id, verification_status=row.verification_status)

    async def set_verification(
        self,
        document_id: UUID,
        *,
        status: str,
        verified_by_user_id: UUID,
        notes: str | None,
    ) -> None:
        """Apply an admin verification decision to a user_documents row.

        Same signature as `DocumentRepository.set_verification` on purpose:
        `DocumentReviewService` picks one repository or the other by source and
        calls this identically for both.
        """
        await self._session.execute(
            text(
                "UPDATE user_documents "
                "SET verification_status = :s, verified_by_user_id = :by, "
                "    verification_notes = :notes, updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"s": status, "by": verified_by_user_id, "notes": notes, "id": document_id},
        )
