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


class ListingDocumentMeta(BaseModel):
    # Verification metadata only — the file is served via the watermarked view
    # route, never here (SCRUM-95 buyer detail-page trust panel).
    document_type: str
    verification_status: str


class ListingDocumentsResponse(BaseModel):
    documents: list[ListingDocumentMeta]


class SellerDocumentItem(BaseModel):
    """A seller's document across their listings (GET /documents/mine —
    SCRUM-98). verification_notes carries the admin's feedback on rejection."""

    id: UUID
    listing_id: UUID
    property_title: str | None
    document_type: str
    verification_status: str
    verification_notes: str | None
    created_at: datetime


class SellerDocumentsResponse(BaseModel):
    data: list[SellerDocumentItem]


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


# ---- Personal documents / My Documents (SCRUM-188) -------------------------

UserDocumentCategory = Literal["identity", "financial", "property", "other"]


class UserDocumentUploadResponse(BaseModel):
    document_id: UUID
    verification_status: str = "pending"


class UserDocumentItem(BaseModel):
    id: UUID
    category: str
    file_name: str
    size_bytes: int
    content_type: str
    # 'failed' is what the design's "Rejected" pill labels — see migration 0003
    # for why the existing status vocabulary is reused rather than extended.
    verification_status: str
    verification_notes: str | None
    created_at: datetime


class UserDocumentsResponse(BaseModel):
    """The list plus every count the page renders.

    Counts are returned by the server rather than derived on the client,
    because the list can be filtered to one category while the sidebar badges
    and stat cards must keep describing the whole collection.
    """

    items: list[UserDocumentItem]
    # Keyed by category / status, always containing EVERY key with 0 for the
    # empty ones — so "Property 0" and "Rejected 0" render as the design draws
    # them instead of silently disappearing.
    category_counts: dict[str, int]
    status_counts: dict[str, int]
    total: int


class UserDocumentViewResponse(BaseModel):
    url: str


class UserDocumentDeleteResponse(BaseModel):
    deleted: bool


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
