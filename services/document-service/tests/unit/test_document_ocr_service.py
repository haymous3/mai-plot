"""DocumentOcrService — extract/store, flag-on-failure, flag-on-no-fields."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.ocr import FakeOcrEngine, OcrResult
from app.services.document_ocr import DocumentOcrService


class _StubDocRepo:
    """Records which write path the service took."""

    def __init__(self, s3_key: str | None = "listings/x/documents/y.pdf") -> None:
        self._s3_key = s3_key
        self.stored: dict[str, str] | None = None
        self.flagged: dict[str, object] | None = None

    async def get_ocr_source(self, document_id: UUID) -> str | None:
        return self._s3_key

    async def store_ocr_result(self, document_id: UUID, data: dict[str, str]) -> None:
        self.stored = data

    async def flag_for_manual_review(
        self, document_id: UUID, *, note: str, data: dict[str, str] | None = None
    ) -> None:
        self.flagged = {"note": note, "data": data}


def _service(repo: _StubDocRepo, engine: FakeOcrEngine) -> DocumentOcrService:
    return DocumentOcrService(engine=engine, documents=repo)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_successful_ocr_stores_extracted_fields() -> None:
    repo = _StubDocRepo()
    outcome = await _service(repo, FakeOcrEngine()).run(uuid4())

    assert outcome.status == "extracted"
    assert outcome.fields == 4
    assert repo.stored is not None
    assert repo.stored["plot_number"] == "LA-1234"
    assert repo.flagged is None


@pytest.mark.asyncio
async def test_engine_failure_flags_for_manual_review() -> None:
    repo = _StubDocRepo()
    outcome = await _service(repo, FakeOcrEngine(fail_next=True)).run(uuid4())

    assert outcome.status == "flagged"
    assert repo.stored is None
    assert repo.flagged is not None
    assert "failed" in str(repo.flagged["note"]).lower()


@pytest.mark.asyncio
async def test_no_usable_fields_flags_for_manual_review() -> None:
    repo = _StubDocRepo()
    blank = FakeOcrEngine(result=OcrResult(raw_text="illegible scan", key_values={}))
    outcome = await _service(repo, blank).run(uuid4())

    assert outcome.status == "flagged"
    assert repo.stored is None
    assert repo.flagged is not None


@pytest.mark.asyncio
async def test_missing_document_is_skipped() -> None:
    repo = _StubDocRepo(s3_key=None)
    outcome = await _service(repo, FakeOcrEngine()).run(uuid4())

    assert outcome.status == "skipped"
    assert repo.stored is None and repo.flagged is None
