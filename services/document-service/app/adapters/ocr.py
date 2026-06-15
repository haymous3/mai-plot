"""OCR engine adapter (AWS Textract) for title documents (SCRUM-55).

Same adapter shape as document_storage / watermark:

  * OcrEngine — Protocol every call site depends on.
  * TextractOcrEngine — real adapter (boto3 Textract over the S3 object).
  * FakeOcrEngine — in-process fake for local + CI; returns canned key/values
    so the pipeline is exercised end-to-end without an AWS call.

The engine returns the raw text + form key/values; turning those into the
business fields (address, plot number, date, issuing authority) is the
parser's job (app/services/ocr_parser.py), kept separate so it is unit-tested
without any AWS dependency.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class OcrEngineError(RuntimeError):
    """The OCR backend itself failed (network / 5xx / credentials / unreadable)."""


@dataclass(frozen=True)
class OcrResult:
    """What an OCR engine returns for one document.

    key_values are normalised lower-cased form keys -> values (Textract FORMS);
    raw_text is the full detected text, used for regex fallbacks.
    """

    raw_text: str
    key_values: dict[str, str] = field(default_factory=dict)


class OcrEngine(Protocol):
    async def extract(self, s3_key: str) -> OcrResult:  # pragma: no cover - protocol
        ...


@dataclass
class FakeOcrEngine:
    """Test/local double. Returns a preset result (default: a plausible C of O)
    so the success path is exercised without AWS. Set fail_next to simulate a
    Textract failure, or pass an empty result to exercise the no-fields path."""

    result: OcrResult | None = None
    fail_next: bool = False

    async def extract(self, s3_key: str) -> OcrResult:
        if self.fail_next:
            self.fail_next = False
            raise OcrEngineError("simulated OCR failure")
        if self.result is not None:
            return self.result
        return OcrResult(
            raw_text=(
                "CERTIFICATE OF OCCUPANCY\n"
                "Property Address: 12 Admiralty Way, Lekki, Lagos\n"
                "Plot Number: LA-1234\n"
                "Date: 2021-07-15\n"
                "Issuing Authority: Lagos State Government\n"
            ),
            key_values={
                "property address": "12 Admiralty Way, Lekki, Lagos",
                "plot number": "LA-1234",
                "date": "2021-07-15",
                "issuing authority": "Lagos State Government",
            },
        )


class TextractOcrEngine:
    """Real adapter over AWS Textract. Untested in CI (no AWS there). boto3 is
    synchronous, so the blocking call runs in a thread. Reads the object
    straight from the private bucket via an S3Object reference (no download)."""

    def __init__(self, *, bucket: str, region: str, endpoint_url: str | None = None) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "textract", region_name=region, endpoint_url=endpoint_url or None
        )

    async def extract(self, s3_key: str) -> OcrResult:
        try:
            response = await asyncio.to_thread(
                self._client.analyze_document,
                Document={"S3Object": {"Bucket": self._bucket, "Name": s3_key}},
                FeatureTypes=["FORMS"],
            )
        except Exception as exc:  # boto3 raises ClientError / BotoCoreError
            logger.error("document.ocr.textract_failed", extra={"s3_key": s3_key})
            raise OcrEngineError(str(exc)) from exc
        return _parse_textract_blocks(response.get("Blocks", []))


def _parse_textract_blocks(blocks: list[dict[str, Any]]) -> OcrResult:
    """Turn Textract's block graph into raw text + KEY_VALUE_SET pairs."""
    by_id = {str(b.get("Id")): b for b in blocks}
    lines: list[str] = []
    key_values: dict[str, str] = {}

    for block in blocks:
        btype = block.get("BlockType")
        if btype == "LINE" and isinstance(block.get("Text"), str):
            lines.append(block["Text"])
        elif btype == "KEY_VALUE_SET" and "KEY" in (block.get("EntityTypes") or []):
            key = _block_text(block, by_id)
            value = _value_text(block, by_id)
            if key:
                key_values[key.strip().lower().rstrip(":")] = value.strip()

    return OcrResult(raw_text="\n".join(lines), key_values=key_values)


def _block_text(block: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    """Concatenate the WORD children of a block via its CHILD relationship."""
    words: list[str] = []
    for rel in block.get("Relationships") or []:
        if not isinstance(rel, dict) or rel.get("Type") != "CHILD":
            continue
        for child_id in rel.get("Ids") or []:
            child = by_id.get(str(child_id), {})
            if child.get("BlockType") == "WORD" and isinstance(child.get("Text"), str):
                words.append(child["Text"])
    return " ".join(words)


def _value_text(key_block: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    """Follow a KEY block's VALUE relationship to its value block's text."""
    for rel in key_block.get("Relationships") or []:
        if not isinstance(rel, dict) or rel.get("Type") != "VALUE":
            continue
        for value_id in rel.get("Ids") or []:
            value_block = by_id.get(str(value_id))
            if value_block is not None:
                return _block_text(value_block, by_id)
    return ""


def build_ocr_engine(*, use_fake: bool, bucket: str, region: str, endpoint_url: str) -> OcrEngine:
    """Factory — fake engine for local/CI, real Textract in production."""
    if use_fake:
        return FakeOcrEngine()
    return TextractOcrEngine(bucket=bucket, region=region, endpoint_url=endpoint_url)
