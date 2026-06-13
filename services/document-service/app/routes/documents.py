"""Listing document routes.

POST /listings/{id}/documents is pathed under /listings per api-contracts.md;
Kong routes that specific path to document-service. Handlers are thin: read
the file, call the service, translate domain errors to the standard envelope.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_document_upload_service
from app.schemas.document import DocumentType, DocumentUploadResponse
from app.security import CurrentUser
from app.services.document import InvalidDocument
from app.services.document_upload import (
    DocumentStorageUnavailable,
    DocumentUploadService,
    ListingNotFound,
    NotListingOwner,
)

router = APIRouter(prefix="/listings", tags=["documents"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post(
    "/{listing_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponse,
)
async def upload_document(
    listing_id: UUID,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[DocumentUploadService, Depends(get_document_upload_service)],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File(description="Legal document — PDF or JPEG")],
) -> DocumentUploadResponse | JSONResponse:
    data = await file.read()
    try:
        result = await service.upload(
            listing_id=listing_id,
            caller=caller,
            document_type=document_type,
            data=data,
        )
    except ListingNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND, "LISTING_NOT_FOUND", "No listing found with that id."
        )
    except NotListingOwner:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LISTING_OWNER",
            "You can only add documents to your own listings.",
        )
    except InvalidDocument as exc:
        # Never echo the document bytes. Literal 422 sidesteps the deprecation rename.
        return _error(422, exc.code, str(exc))
    except DocumentStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "Document storage is temporarily unavailable. Please retry.",
        )

    return DocumentUploadResponse(
        document_id=result.document_id, verification_status=result.verification_status
    )
