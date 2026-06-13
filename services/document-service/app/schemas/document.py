"""Request/response models for the document endpoints."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

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
