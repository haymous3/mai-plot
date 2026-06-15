"""Document OCR orchestration (SCRUM-55) — the logic the Celery task runs.

For one uploaded document: run OCR, parse the title fields, and persist them
as JSONB. The operation is failure-tolerant by design (AC: an OCR failure must
not block listing/document creation and must flag the doc for manual review):

  * engine/parse succeeds with usable fields -> store ocr_extracted_data,
    leave verification_status as-is (a human still verifies).
  * engine fails, or no usable field is extracted -> store whatever was read
    and move the document to 'under_review' with a note.

run() therefore never raises — failure is an outcome it records, not an error
it propagates. Kept free of Celery so it is unit/integration-tested directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.ocr import OcrEngine, OcrEngineError
from app.repositories.document_repo import DocumentRepository
from app.services.ocr_parser import parse_fields

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrOutcome:
    document_id: UUID
    status: str  # 'extracted' | 'flagged' | 'skipped'
    fields: int


class DocumentOcrService:
    def __init__(self, *, engine: OcrEngine, documents: DocumentRepository) -> None:
        self._engine = engine
        self._documents = documents

    async def run(self, document_id: UUID) -> OcrOutcome:
        s3_key = await self._documents.get_ocr_source(document_id)
        if s3_key is None:
            logger.info("document.ocr.skipped_missing", extra={"document_id": str(document_id)})
            return OcrOutcome(document_id=document_id, status="skipped", fields=0)

        try:
            result = await self._engine.extract(s3_key)
        except OcrEngineError:
            # Backend failure — flag for manual review (AC), never raise.
            await self._documents.flag_for_manual_review(
                document_id, note="OCR engine failed; needs manual review."
            )
            logger.warning("document.ocr.engine_failed", extra={"document_id": str(document_id)})
            return OcrOutcome(document_id=document_id, status="flagged", fields=0)

        fields = parse_fields(result)
        if not fields:
            # Nothing usable extracted — flag for manual review.
            await self._documents.flag_for_manual_review(
                document_id, note="OCR extracted no usable fields; needs manual review."
            )
            logger.info("document.ocr.no_fields", extra={"document_id": str(document_id)})
            return OcrOutcome(document_id=document_id, status="flagged", fields=0)

        await self._documents.store_ocr_result(document_id, fields)
        logger.info(
            "document.ocr.extracted",
            extra={"document_id": str(document_id), "field_count": len(fields)},
        )
        return OcrOutcome(document_id=document_id, status="extracted", fields=len(fields))
