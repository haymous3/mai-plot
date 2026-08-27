"""Personal-document routes — My Documents (SCRUM-188).

⚠️ Pathed `/documents/personal`, NOT `/documents/mine`. That path is already
taken by the SELLER documents list (SCRUM-98), which returns every document
across the caller's listings — a different collection with a different owner
model. Two endpoints both meaning "mine" would be a permanent source of
confusion, so this one says what it actually is: documents belonging to the
person rather than to their listings.

Kong routes the whole `/documents` prefix, so these need no gateway change.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_user_document_service
from app.schemas.document import (
    UserDocumentCategory,
    UserDocumentDeleteResponse,
    UserDocumentItem,
    UserDocumentsResponse,
    UserDocumentUploadResponse,
    UserDocumentViewResponse,
)
from app.security import CurrentUser
from app.services.document import InvalidDocument
from app.services.user_documents import (
    UserDocumentNotFound,
    UserDocumentService,
    UserDocumentStorageUnavailable,
)

router = APIRouter(prefix="/documents/personal", tags=["user-documents"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


ServiceDep = Annotated[UserDocumentService, Depends(get_user_document_service)]
CallerDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserDocumentUploadResponse)
async def upload_document(
    caller: CallerDep,
    service: ServiceDep,
    category: Annotated[UserDocumentCategory, Form()],
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG")],
) -> UserDocumentUploadResponse | JSONResponse:
    """Upload one personal document (SCRUM-188).

    The format is decided by MAGIC BYTES, not the filename or the browser's
    Content-Type. The client-supplied filename is kept only as a display label.

    Lands as `pending`; an admin review workflow follows in a later ticket, so
    nothing here can set a document verified.
    """
    data = await file.read()
    try:
        document_id = await service.upload(
            user_id=caller.user_id,
            category=category,
            file_name=file.filename or "",
            data=data,
        )
    except InvalidDocument as exc:
        # Never echo the file bytes. Literal 422 sidesteps the
        # status.HTTP_422_* deprecation rename.
        return _error(422, exc.code, str(exc))
    except UserDocumentStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "Document storage is temporarily unavailable. Please retry.",
        )
    return UserDocumentUploadResponse(document_id=document_id)


@router.get("", response_model=UserDocumentsResponse)
async def list_documents(
    caller: CallerDep,
    service: ServiceDep,
    category: Annotated[UserDocumentCategory | None, Query()] = None,
) -> UserDocumentsResponse | JSONResponse:
    """The caller's documents plus the counts the page renders.

    `category` filters the LIST only — the counts always describe the whole
    collection, so the sidebar badges and stat cards stay correct while a tab
    is selected.
    """
    try:
        summary = await service.summary(user_id=caller.user_id, category=category)
    except InvalidDocument as exc:
        return _error(422, exc.code, str(exc))

    return UserDocumentsResponse(
        items=[
            UserDocumentItem(
                id=d.id,
                category=d.category,
                file_name=d.file_name,
                size_bytes=d.size_bytes,
                content_type=d.content_type,
                verification_status=d.verification_status,
                verification_notes=d.verification_notes,
                created_at=d.created_at,
            )
            for d in summary.documents
        ],
        category_counts=summary.category_counts,
        status_counts=summary.status_counts,
        total=summary.total,
    )


@router.get("/{document_id}/view", response_model=UserDocumentViewResponse)
async def view_document(
    document_id: UUID,
    caller: CallerDep,
    service: ServiceDep,
) -> UserDocumentViewResponse | JSONResponse:
    """A short-TTL pre-signed URL for one of the caller's own documents.

    404 — not 403 — when the document belongs to someone else. Ownership is
    part of the query, so "not yours" and "does not exist" are deliberately
    indistinguishable; a 403 would confirm the id is real.
    """
    try:
        url = await service.view_url(document_id=document_id, user_id=caller.user_id)
    except UserDocumentNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")
    return UserDocumentViewResponse(url=url)


@router.delete("/{document_id}", response_model=UserDocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    caller: CallerDep,
    service: ServiceDep,
) -> UserDocumentDeleteResponse | JSONResponse:
    """Remove one of the caller's documents from their list.

    Soft-delete; the stored object is deliberately retained (see
    `UserDocumentService.delete`). Not idempotent by design — a second delete
    404s, so the UI can tell "removed" from "was never there".
    """
    try:
        await service.delete(document_id=document_id, user_id=caller.user_id)
    except UserDocumentNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "Document not found.")
    return UserDocumentDeleteResponse(deleted=True)
