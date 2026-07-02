"""Buyer loan-document routes (SCRUM-131).

POST /loans/{loan_id}/documents — the buyer (or an admin) attaches an application
document (bank statement / employment letter / passport). GET lists them with
short-TTL pre-signed URLs. Pathed under /loans; Kong routes this specific suffix
to document-service (the rest of /loans is loan-service).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_loan_document_service
from app.schemas.document import (
    LoanDocumentItem,
    LoanDocumentsResponse,
    LoanDocumentType,
    LoanDocumentUploadResponse,
)
from app.security import CurrentUser
from app.services.document import InvalidDocument
from app.services.loan_document_upload import (
    LoanDocumentService,
    LoanDocumentStorageUnavailable,
    LoanNotFound,
    NotLoanOwner,
)

router = APIRouter(prefix="/loans", tags=["loan-documents"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


ServiceDep = Annotated[LoanDocumentService, Depends(get_loan_document_service)]
CallerDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post(
    "/{loan_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=LoanDocumentUploadResponse,
)
async def upload_loan_document(
    loan_id: UUID,
    caller: CallerDep,
    service: ServiceDep,
    document_type: Annotated[LoanDocumentType, Form()],
    file: Annotated[UploadFile, File(description="Application document — PDF, JPEG, or PNG")],
) -> LoanDocumentUploadResponse | JSONResponse:
    data = await file.read()
    try:
        result = await service.upload(
            loan_id=loan_id, caller=caller, document_type=document_type, data=data
        )
    except LoanNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LOAN_NOT_FOUND", "No loan found with that id.")
    except NotLoanOwner:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LOAN_OWNER",
            "You can only add documents to your own loan application.",
        )
    except InvalidDocument as exc:
        return _error(422, exc.code, str(exc))
    except LoanDocumentStorageUnavailable:
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "Document storage is temporarily unavailable. Please retry.",
        )
    return LoanDocumentUploadResponse(
        document_id=result.document_id, verification_status=result.verification_status
    )


@router.get("/{loan_id}/documents", response_model=None)
async def list_loan_documents(
    loan_id: UUID,
    caller: CallerDep,
    service: ServiceDep,
) -> LoanDocumentsResponse | JSONResponse:
    try:
        views = await service.list_for_loan(loan_id=loan_id, caller=caller)
    except LoanNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LOAN_NOT_FOUND", "No loan found with that id.")
    except NotLoanOwner:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LOAN_OWNER",
            "You can only view your own loan's documents.",
        )
    return LoanDocumentsResponse(
        items=[
            LoanDocumentItem(
                id=v.id,
                document_type=v.document_type,
                verification_status=v.verification_status,
                created_at=v.created_at,
                url=v.url,
            )
            for v in views
        ]
    )
