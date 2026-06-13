"""Document view route — GET /documents/{id}/view.

Serves a verified document's watermarked bytes to an authenticated caller.
The S3 object is never exposed; the API streams the watermarked content.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response

from app.dependencies import get_current_user, get_document_view_service
from app.security import CurrentUser
from app.services.document_view import (
    DocumentNotFound,
    DocumentNotViewable,
    DocumentStorageUnavailable,
    DocumentViewService,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/{document_id}/view")
async def view_document(
    document_id: UUID,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[DocumentViewService, Depends(get_document_view_service)],
) -> Response:
    try:
        rendered = await service.render(document_id=document_id, viewer=caller)
    except DocumentNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "DOCUMENT_NOT_FOUND", "No document found with that id."
        )
    except DocumentNotViewable:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "DOCUMENT_NOT_VERIFIED",
            "This document has not been verified and cannot be viewed.",
        )
    except DocumentStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "The document is temporarily unavailable. Please retry.",
        )

    return Response(content=rendered.content, media_type=rendered.content_type)
