"""Watermarker adapters — fake (used in serving) + real smoke tests."""

from __future__ import annotations

import io

from app.adapters.watermark import FakeWatermarker, RealWatermarker


def test_fake_embeds_overlay_text() -> None:
    out = FakeWatermarker().apply(data=b"original", content_type="application/pdf", overlay="Ada")
    assert b"WMARK[Ada]" in out
    assert b"original" in out


def test_real_watermarks_png() -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (255, 255, 255)).save(buf, format="PNG")
    original = buf.getvalue()

    out = RealWatermarker().apply(data=original, content_type="image/png", overlay="Ada • now")
    assert out != original
    # Still a valid image.
    assert Image.open(io.BytesIO(out)).size == (50, 50)


def test_real_watermarks_pdf() -> None:
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 100, "deed of assignment")
    c.save()
    original = buf.getvalue()

    out = RealWatermarker().apply(data=original, content_type="application/pdf", overlay="Ada")
    # Still a valid single-page PDF.
    assert len(PdfReader(io.BytesIO(out)).pages) == 1
