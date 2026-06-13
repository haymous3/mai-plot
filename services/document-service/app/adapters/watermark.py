"""Document watermarking adapter.

CLAUDE.md non-negotiable: a buyer-name + timestamp overlay is applied before
a document is served to a buyer. Adapter shape mirrors the storage adapter:

  * Watermarker — Protocol every call site depends on.
  * RealWatermarker — Pillow for images, pypdf + reportlab for PDFs.
  * FakeWatermarker — in-process fake for local + CI; embeds the overlay text
    so tests can assert the watermark was applied without image/PDF libs.
"""

from __future__ import annotations

import io
from typing import Protocol


class WatermarkError(RuntimeError):
    """Raised when watermarking fails (unexpected/corrupt input)."""


class Watermarker(Protocol):
    def apply(
        self, *, data: bytes, content_type: str, overlay: str
    ) -> bytes:  # pragma: no cover - protocol
        ...


class FakeWatermarker:
    """Test double. Prepends a recognisable marker carrying the overlay text
    so a test can assert the served bytes were watermarked (and with whom)."""

    def apply(self, *, data: bytes, content_type: str, overlay: str) -> bytes:
        return b"WMARK[" + overlay.encode("utf-8") + b"]" + data


class RealWatermarker:
    """Applies a visible overlay. Untested in CI (image/PDF libs); the fake
    covers the wiring. Imports are lazy so the libs load only in production."""

    def apply(self, *, data: bytes, content_type: str, overlay: str) -> bytes:
        try:
            if content_type == "application/pdf":
                return self._watermark_pdf(data, overlay)
            if content_type in ("image/jpeg", "image/png"):
                return self._watermark_image(data, content_type, overlay)
        except Exception as exc:  # corrupt input / lib failure
            raise WatermarkError(str(exc)) from exc
        raise WatermarkError(f"unsupported content type: {content_type}")

    def _watermark_image(self, data: bytes, content_type: str, overlay: str) -> bytes:
        from PIL import Image, ImageDraw

        image = Image.open(io.BytesIO(data)).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.text((10, 10), overlay, fill=(255, 0, 0))
        out = io.BytesIO()
        image.save(out, format="JPEG" if content_type == "image/jpeg" else "PNG")
        return out.getvalue()

    def _watermark_pdf(self, data: bytes, overlay: str) -> bytes:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas

        stamp_buf = io.BytesIO()
        c = canvas.Canvas(stamp_buf)
        c.setFillColorRGB(1, 0, 0)
        c.drawString(20, 20, overlay)
        c.save()
        stamp_buf.seek(0)
        stamp_page = PdfReader(stamp_buf).pages[0]

        # Attach the source pages to the writer FIRST, then merge the stamp
        # onto the writer's pages (pypdf deprecates merging onto detached pages).
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(data)))
        for page in writer.pages:
            page.merge_page(stamp_page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()


def build_watermarker(*, use_fake: bool) -> Watermarker:
    """Factory — fake for local/CI, real overlay in production."""
    if use_fake:
        return FakeWatermarker()
    return RealWatermarker()
