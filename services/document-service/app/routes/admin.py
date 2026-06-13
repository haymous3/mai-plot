"""/admin/documents routes (admin JWT + IP whitelist gated).

Backend for the legal-team document review: the queue of pending documents
and the verify/reject decision.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_admin_queue_service,
    get_document_review_service,
    require_admin,
)
from app.schemas.document import DocQueueResponse, DocReviewRequest, DocReviewResponse
from app.security import CurrentUser
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocQueueResponse:
    return await service.list_queue(status=verification_status, page=page, page_size=page_size)


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
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except DocumentNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "No document found with that id."
        )
    except DocumentNotPending:
        return _error(422, "DOCUMENT_NOT_PENDING", "Only a pending document can be reviewed.")
    except NotesRequired:
        return _error(422, "NOTES_REQUIRED_FOR_REJECTION", "A rejection must include notes.")

    return DocReviewResponse(
        document_id=result.document_id, verification_status=result.verification_status
    )
