"""Schemas for inspection report submission/viewing (SCRUM-73).

Submission is multipart (checklist Form fields + photo files + GPS), so its
inputs are Form() params on the route, not a JSON body model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.repositories.inspection_repo import InspectionRow, ReportReviewRow
from app.services.report_service import ReportView


class ReportSubmitResponse(BaseModel):
    inspection_id: UUID
    status: str
    report_submitted_at: datetime | None

    @classmethod
    def from_row(cls, row: InspectionRow) -> ReportSubmitResponse:
        return cls(
            inspection_id=row.id,
            status=row.status,
            report_submitted_at=row.report_submitted_at,
        )


class ReportResponse(BaseModel):
    inspection_id: UUID
    status: str
    report_submitted_at: datetime | None
    gps_lat: float | None
    gps_lng: float | None
    property_condition: str | None
    amenities: list[str]
    discrepancies: str | None
    remarks: str | None
    photo_urls: list[str]
    # Short-TTL pre-signed URL of the optional inspection video (SCRUM-142), or
    # None when no video was uploaded.
    video_url: str | None = None

    @classmethod
    def from_view(cls, view: ReportView) -> ReportResponse:
        return cls(
            inspection_id=view.inspection_id,
            status=view.status,
            report_submitted_at=view.report_submitted_at,
            gps_lat=view.gps_lat,
            gps_lng=view.gps_lng,
            property_condition=view.property_condition,
            amenities=view.amenities,
            discrepancies=view.discrepancies,
            remarks=view.remarks,
            photo_urls=view.photo_urls,
            video_url=view.video_url,
        )


class ReportReviewRequest(BaseModel):
    """An admin decision on a submitted report (SCRUM-205). `note` is required
    when rejecting — the service enforces it, so a missing note is a 422 with a
    reason rather than a silent rejection the realtor cannot act on."""

    action: Literal["approve", "reject"]
    note: str | None = None


class ReportReviewResponse(BaseModel):
    inspection_id: UUID
    report_review_status: str


class ReportReviewItem(BaseModel):
    """One row of the admin review queue (SCRUM-205). The realtor is identified
    by name + ESVARBON licence only — never contact details (CLAUDE.md §10)."""

    inspection_id: UUID
    transaction_id: UUID
    realtor_id: UUID
    realtor_name: str | None
    esvarbon_number: str | None
    report_submitted_at: datetime | None
    report_review_status: str
    report_reviewed_at: datetime | None
    report_review_note: str | None
    report_revision: int
    property_title: str | None
    address_text: str | None
    lga: str | None
    state: str | None

    @classmethod
    def from_row(cls, row: ReportReviewRow) -> ReportReviewItem:
        return cls(
            inspection_id=row.inspection_id,
            transaction_id=row.transaction_id,
            realtor_id=row.realtor_id,
            realtor_name=row.realtor_name,
            esvarbon_number=row.esvarbon_number,
            report_submitted_at=row.report_submitted_at,
            report_review_status=row.report_review_status,
            report_reviewed_at=row.report_reviewed_at,
            report_review_note=row.report_review_note,
            report_revision=row.report_revision,
            property_title=row.property_title,
            address_text=row.address_text,
            lga=row.lga,
            state=row.state,
        )


class ReportReviewQueueResponse(BaseModel):
    data: list[ReportReviewItem]

    @classmethod
    def from_rows(cls, rows: list[ReportReviewRow]) -> ReportReviewQueueResponse:
        return cls(data=[ReportReviewItem.from_row(r) for r in rows])
