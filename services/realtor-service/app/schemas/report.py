"""Schemas for inspection report submission/viewing (SCRUM-73).

Submission is multipart (checklist Form fields + photo files + GPS), so its
inputs are Form() params on the route, not a JSON body model.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.inspection_repo import InspectionRow
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
