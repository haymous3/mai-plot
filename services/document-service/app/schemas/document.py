"""Request/response models for the document endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# The document types a seller may upload via the API (poa/other are internal).
DocumentType = Literal[
    "c_of_o",
    "deed_of_assignment",
    "survey_plan",
    "governors_consent",
    "receipt",
]


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    verification_status: str = "pending"


# ---- Buyer loan documents (SCRUM-131) --------------------------------------

LoanDocumentType = Literal["bank_statement", "employment_letter", "passport"]


class LoanDocumentUploadResponse(BaseModel):
    document_id: UUID
    verification_status: str = "pending"


class LoanDocumentItem(BaseModel):
    id: UUID
    document_type: str
    verification_status: str
    created_at: datetime
    url: str


class LoanDocumentsResponse(BaseModel):
    items: list[LoanDocumentItem]


# ---- Admin verification ----------------------------------------------------

ReviewAction = Literal["verify", "reject"]


class DocQueueItem(BaseModel):
    id: UUID
    listing_id: UUID
    document_type: str
    verification_status: str
    created_at: datetime


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class DocQueueResponse(BaseModel):
    data: list[DocQueueItem]
    pagination: Pagination


class DocReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: ReviewAction
    # Required for reject (enforced in the service for a specific code).
    notes: str | None = Field(default=None, max_length=2000)


class DocReviewResponse(BaseModel):
    document_id: UUID
    verification_status: str
