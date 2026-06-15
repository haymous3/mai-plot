"""OCR dispatch seam (SCRUM-55).

The upload path calls `enqueue(document_id)` to kick off OCR without doing the
(slow, external) Textract call on the request. Two transports share one
Protocol:

  * CeleryOcrDispatcher — production. Hands the document id to the
    `run_document_ocr` Celery task. Enqueue is best-effort: a broker hiccup is
    logged, never raised, so OCR dispatch can't fail the upload (AC: OCR
    failure must not block document creation).
  * InlineOcrDispatcher — local/CI. Runs the same DocumentOcrService inline
    against the request's session + a fake engine, so the pipeline is exercised
    without a broker or AWS.

`build_ocr_dispatcher` picks the transport from settings (`ocr_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.adapters.ocr import OcrEngine
from app.repositories.document_repo import DocumentRepository
from app.services.document_ocr import DocumentOcrService

logger = logging.getLogger(__name__)


class OcrDispatcher(Protocol):
    async def enqueue(self, document_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CeleryOcrDispatcher:
    """Production transport — dispatch OCR to a Celery worker."""

    async def enqueue(self, document_id: UUID) -> None:
        # Imported lazily so the request path (and tests) never import Celery
        # task wiring unless this transport is actually used.
        try:
            from app.tasks.document_ocr import run_document_ocr

            run_document_ocr.delay(str(document_id))
        except Exception as exc:  # broker down etc. — never fail the upload
            logger.warning(
                "document.ocr.enqueue_failed",
                extra={"document_id": str(document_id), "error": str(exc)},
            )


class InlineOcrDispatcher:
    """Local/CI transport — run OCR inline (failure-tolerant), no broker."""

    def __init__(self, *, service: DocumentOcrService) -> None:
        self._service = service

    async def enqueue(self, document_id: UUID) -> None:
        await self._service.run(document_id)


def build_ocr_dispatcher(
    *, via_celery: bool, engine: OcrEngine, documents: DocumentRepository
) -> OcrDispatcher:
    if via_celery:
        return CeleryOcrDispatcher()
    return InlineOcrDispatcher(service=DocumentOcrService(engine=engine, documents=documents))
