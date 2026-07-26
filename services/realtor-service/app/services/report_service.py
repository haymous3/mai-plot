"""Inspection report submission + viewing (SCRUM-73).

The assigned realtor submits a structured report after the confirmed inspection
date: GPS (validated within 1km of the property), a checklist, and >=3 photos
(stored in the private bucket). The report is then visible to the buyer, seller,
admin, and the realtor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.adapters.document_storage import DocumentStorage, DocumentStorageError
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.inspection_repo import InspectionRepository, InspectionRow
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser
from app.services.credentials import (
    InvalidCredential,
    detect_photo_type,
    validate_coordinates,
    validate_photo_size,
)
from app.services.inspection_service import InspectionNotFound, NotAssignedRealtor

logger = logging.getLogger(__name__)

_VALID_CONDITIONS = {"excellent", "good", "fair", "poor"}


class ReportError(RuntimeError):
    pass


class ReportNotSubmittable(ReportError):
    """The inspection isn't in 'accepted' state (e.g. already reported)."""


class ReportTooEarly(ReportError):
    """The confirmed inspection date hasn't arrived yet."""


class GpsOutOfRange(ReportError):
    """The submitted GPS isn't within range of the property."""


class NotAuthorizedForReport(ReportError):
    """Caller may not view this report (not a party / realtor / admin)."""


class ReportNotFound(ReportError):
    """No report has been submitted for this inspection yet."""


@dataclass(frozen=True)
class ReportView:
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


class ReportService:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        transactions: TransactionRepository,
        audit: AuditLogRepository,
        storage: DocumentStorage,
        gps_radius_meters: float,
        min_photos: int,
        photo_max_bytes: int,
        presign_ttl_seconds: int,
    ) -> None:
        self._inspections = inspections
        self._transactions = transactions
        self._audit = audit
        self._storage = storage
        self._gps_radius = gps_radius_meters
        self._min_photos = min_photos
        self._photo_max_bytes = photo_max_bytes
        self._presign_ttl = presign_ttl_seconds

    async def submit(
        self,
        *,
        caller: CurrentUser,
        inspection_id: UUID,
        gps_lat: float,
        gps_lng: float,
        property_condition: str,
        amenities: list[str],
        discrepancies: str | None,
        remarks: str | None,
        photos: list[bytes],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InspectionRow:
        inspection = await self._inspections.get(inspection_id)
        if inspection is None:
            raise InspectionNotFound()
        if inspection.realtor_id != caller.user_id:
            raise NotAssignedRealtor()
        # A rescheduled inspection is confirmed at its new time (SCRUM-141), so it
        # is reportable just like an accepted one.
        if inspection.status not in ("accepted", "rescheduled"):
            raise ReportNotSubmittable()
        if inspection.confirmed_date is None or datetime.now(UTC) < inspection.confirmed_date:
            raise ReportTooEarly()

        # Validate the checklist + photos (InvalidCredential -> 422).
        if property_condition not in _VALID_CONDITIONS:
            raise InvalidCredential("CONDITION_INVALID", "property_condition is not a valid value.")
        if len(photos) < self._min_photos:
            raise InvalidCredential(
                "MIN_PHOTOS_REQUIRED", f"At least {self._min_photos} photos are required."
            )
        validate_coordinates(gps_lat, gps_lng)

        # GPS must be within range of the property (via the transaction's listing).
        txn = await self._transactions.get(inspection.transaction_id)
        if txn is None:
            raise InspectionNotFound()
        within = await self._inspections.is_point_within_property(
            listing_id=txn.listing_id, lat=gps_lat, lng=gps_lng, meters=self._gps_radius
        )
        if not within:
            raise GpsOutOfRange()

        photo_keys: list[str] = []
        for photo in photos:
            validate_photo_size(photo, max_bytes=self._photo_max_bytes)
            content_type, extension = detect_photo_type(photo)
            key = f"inspection-report/{inspection_id}/{uuid4()}.{extension}"
            try:
                await self._storage.put(key=key, data=photo, content_type=content_type)
            except DocumentStorageError as exc:
                logger.error(
                    "inspection.report.storage_failed", extra={"inspection_id": str(inspection_id)}
                )
                raise ReportError("photo storage failed") from exc
            photo_keys.append(key)

        report_data = {
            "property_condition": property_condition,
            "amenities": amenities,
            "discrepancies": discrepancies,
            "remarks": remarks,
            "photo_keys": photo_keys,
        }
        await self._inspections.submit_report(
            inspection_id, gps_lat=gps_lat, gps_lng=gps_lng, report_data=report_data
        )
        await self._audit.record(
            actor_id=caller.user_id,
            actor_role=caller.role,
            action="inspection.report_submitted",
            entity_type="inspection",
            entity_id=inspection_id,
            new_value={"photo_count": len(photo_keys), "transaction_id": str(txn.id)},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("inspection.report_submitted", extra={"inspection_id": str(inspection_id)})
        updated = await self._inspections.get(inspection_id)
        assert updated is not None
        return updated

    async def get_report(self, *, caller: CurrentUser, inspection_id: UUID) -> ReportView:
        inspection = await self._inspections.get(inspection_id)
        if inspection is None:
            raise InspectionNotFound()

        txn = await self._transactions.get(inspection.transaction_id)
        parties = {inspection.realtor_id}
        if txn is not None:
            parties |= {txn.buyer_id, txn.seller_id}
        if caller.role != "admin" and caller.user_id not in parties:
            raise NotAuthorizedForReport()

        if inspection.report_submitted_at is None or inspection.report_data is None:
            raise ReportNotFound()

        data = inspection.report_data
        photo_urls = [
            self._storage.presigned_get_url(key, expires_seconds=self._presign_ttl)
            for key in data.get("photo_keys", [])
        ]
        return ReportView(
            inspection_id=inspection.id,
            status=inspection.status,
            report_submitted_at=inspection.report_submitted_at,
            gps_lat=float(inspection.gps_lat) if inspection.gps_lat is not None else None,
            gps_lng=float(inspection.gps_lng) if inspection.gps_lng is not None else None,
            property_condition=data.get("property_condition"),
            amenities=list(data.get("amenities") or []),
            discrepancies=data.get("discrepancies"),
            remarks=data.get("remarks"),
            photo_urls=photo_urls,
        )
