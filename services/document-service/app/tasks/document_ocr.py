"""Celery task: OCR one uploaded document (SCRUM-55).

Thin wrapper around DocumentOcrService — builds a fresh async session + OCR
engine for the worker process and runs the (async) OCR inside asyncio.run().
The logic + tests live in app/services/document_ocr.py.

The service is failure-tolerant (it flags the document for manual review on
failure rather than raising), so this task does not autoretry — an OCR failure
is a recorded outcome, not a transient error to retry.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.ocr import build_ocr_engine
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.document_repo import DocumentRepository
from app.services.document_ocr import DocumentOcrService


async def _run(document_id: UUID) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ocr_engine = build_ocr_engine(
        use_fake=settings.ocr_use_fake,
        bucket=settings.doc_s3_bucket,
        region=settings.doc_s3_region,
        endpoint_url=settings.doc_s3_endpoint_url,
    )
    try:
        async with sessionmaker() as session:
            service = DocumentOcrService(engine=ocr_engine, documents=DocumentRepository(session))
            outcome = await service.run(document_id)
            await session.commit()
    finally:
        await engine.dispose()
    return outcome.status


# Celery's .task decorator is untyped; the wrapped function's own signature is
# explicit, so silence mypy's untyped-decorator complaint just here.
@celery_app.task(name="app.tasks.document_ocr.run_document_ocr")  # type: ignore[untyped-decorator]
def run_document_ocr(document_id: str) -> str:
    """Run the OCR pipeline for a single uploaded document."""
    return asyncio.run(_run(UUID(document_id)))
