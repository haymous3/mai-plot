"""Payment-receipt storage (SCRUM-86) — private S3, never public.

A disbursement writes an immutable JSON receipt (CLAUDE.md / review.md P10).
Mirrors the document_storage adapters: an in-memory fake for local/CI and a real
S3 adapter that PUTs to a PRIVATE bucket. Receipt bytes never get logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


class ReceiptStorageError(RuntimeError):
    """The storage backend itself failed."""


def render_receipt_pdf(title: str, fields: dict[str, Any]) -> bytes:
    """Render a simple one-page PDF receipt (reportlab — pure Python). Returns
    the PDF bytes (start with b'%PDF')."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 80
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(60, y, "Maiplot")
    pdf.setFont("Helvetica", 13)
    pdf.drawString(60, y - 24, title)
    y -= 70
    pdf.setFont("Helvetica", 11)
    for key, value in fields.items():
        pdf.drawString(60, y, f"{key}: {value}")
        y -= 20
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class ReceiptStorage(Protocol):
    async def write_receipt(
        self, payment_event_id: UUID, data: dict[str, Any]
    ) -> str:  # pragma: no cover - protocol
        ...

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, Any]
    ) -> str:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryReceiptStorage:
    """Test double — holds receipts in a dict keyed by object key."""

    receipts: dict[str, bytes] = field(default_factory=dict)

    async def write_receipt(self, payment_event_id: UUID, data: dict[str, Any]) -> str:
        key = f"receipts/{payment_event_id}.json"
        self.receipts[key] = json.dumps(data, separators=(",", ":")).encode()
        return key

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, Any]
    ) -> str:
        key = f"receipts/{payment_event_id}.pdf"
        self.receipts[key] = render_receipt_pdf(title, fields)
        return key


class S3ReceiptStorage:
    """PUTs receipts into a PRIVATE S3 bucket. boto3 is sync, so the call runs in
    a thread."""

    def __init__(self, *, bucket: str, region: str, endpoint_url: str | None = None) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url or None)

    async def write_receipt(self, payment_event_id: UUID, data: dict[str, Any]) -> str:
        key = f"receipts/{payment_event_id}.json"
        body = json.dumps(data, separators=(",", ":")).encode()
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        except Exception as exc:  # boto3 ClientError/BotoCoreError
            logger.error("receipt.storage.put_failed", extra={"key": key})
            raise ReceiptStorageError(str(exc)) from exc
        return key

    async def write_pdf_receipt(
        self, payment_event_id: UUID, *, title: str, fields: dict[str, Any]
    ) -> str:
        key = f"receipts/{payment_event_id}.pdf"
        body = render_receipt_pdf(title, fields)
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/pdf",
            )
        except Exception as exc:
            logger.error("receipt.storage.put_failed", extra={"key": key})
            raise ReceiptStorageError(str(exc)) from exc
        return key


def build_receipt_storage(
    *, use_fake: bool, bucket: str, region: str, endpoint_url: str
) -> ReceiptStorage:
    if use_fake:
        return InMemoryReceiptStorage()
    return S3ReceiptStorage(bucket=bucket, region=region, endpoint_url=endpoint_url)
