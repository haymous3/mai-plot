"""/admin/documents routes (admin JWT + IP whitelist gated).

Backend for the legal-team document review: the queue of pending documents
and the verify/reject decision.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, Response

from app.dependencies import (
    get_admin_document_file_service,
    get_admin_queue_service,
    get_document_review_service,
    require_admin,
)
from app.schemas.document import (
    DocQueueResponse,
    DocReviewRequest,
    DocReviewResponse,
    DocSource,
)
from app.security import CurrentUser
from app.services.admin_document_file import (
    AdminDocumentFileService,
    DocumentUnavailable,
)
from app.services.admin_document_file import (
    DocumentNotFound as ReviewFileNotFound,
)
from app.services.admin_queue import AdminQueueService
from app.services.document_review import (
    DocumentNotFound,
    DocumentNotPending,
    DocumentReviewService,
    NotesRequired,
)

router = APIRouter(prefix="/admin/documents", tags=["admin"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/queue", response_model=DocQueueResponse)
async def review_queue(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[AdminQueueService, Depends(get_admin_queue_service)],
    verification_status: Annotated[str, Query(alias="status")] = "pending",
    source: DocSource = "listing",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocQueueResponse:
    return await service.list_queue(
        source=source, status=verification_status, page=page, page_size=page_size
    )


@router.post("/{document_id}/review", response_model=DocReviewResponse)
async def review_document(
    document_id: UUID,
    body: DocReviewRequest,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[DocumentReviewService, Depends(get_document_review_service)],
) -> DocReviewResponse | JSONResponse:
    try:
        result = await service.review(
            document_id=document_id,
            admin=admin,
            action=body.action,
            notes=body.notes,
            source=body.source,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except DocumentNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "No document found with that id."
        )
    except DocumentNotPending:
        return _error(
            422,
            "DOCUMENT_NOT_PENDING",
            "Only a pending or under-review document can be reviewed.",
        )
    except NotesRequired:
        return _error(422, "NOTES_REQUIRED_FOR_REJECTION", "A rejection must include notes.")

    return DocReviewResponse(
        document_id=result.document_id,
        verification_status=result.verification_status,
        source=result.source,
    )


@router.get("/{document_id}/file")
async def review_file(
    document_id: UUID,
    request: Request,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    service: Annotated[AdminDocumentFileService, Depends(get_admin_document_file_service)],
    source: DocSource = "listing",
) -> Response:
    """Stream a document to a reviewer, verified or not.

    Deliberately separate from `GET /documents/{id}/view`, which serves only
    VERIFIED documents to buyers and sellers. A reviewer must see the
    unverified ones — that is the job — so the two audiences get two routes
    rather than one route with a role branch inside its guard.
    """
    try:
        doc = await service.get_file(
            document_id=document_id,
            viewer=admin,
            source=source,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ReviewFileNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "No document found with that id."
        )
    except DocumentUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "The document is temporarily unavailable. Please retry.",
        )

    return Response(
        content=doc.content,
        media_type=doc.content_type,
        # inline so the admin UI can render it in an iframe/object rather than
        # triggering a download the reviewer then has to clean off their disk.
        headers={"Content-Disposition": f'inline; filename="{doc.file_name}"'},
    )
