"""OCR dispatch — factory picks transport; enqueue never breaks the upload."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.ocr import FakeOcrEngine
from app.services.ocr_dispatch import (
    CeleryOcrDispatcher,
    InlineOcrDispatcher,
    build_ocr_dispatcher,
)


class _RecordingService:
    def __init__(self) -> None:
        self.ran: list[UUID] = []

    async def run(self, document_id: UUID) -> None:
        self.ran.append(document_id)


def test_factory_picks_inline_for_dev_and_celery_for_prod() -> None:
    engine = FakeOcrEngine()
    inline = build_ocr_dispatcher(via_celery=False, engine=engine, documents=None)  # type: ignore[arg-type]
    celery = build_ocr_dispatcher(via_celery=True, engine=engine, documents=None)  # type: ignore[arg-type]
    assert isinstance(inline, InlineOcrDispatcher)
    assert isinstance(celery, CeleryOcrDispatcher)


@pytest.mark.asyncio
async def test_inline_dispatch_runs_ocr_inline() -> None:
    rec = _RecordingService()
    doc_id = uuid4()
    await InlineOcrDispatcher(service=rec).enqueue(doc_id)  # type: ignore[arg-type]
    assert rec.ran == [doc_id]


@pytest.mark.asyncio
async def test_celery_enqueue_is_best_effort_when_broker_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broker failure on .delay() must be swallowed — OCR dispatch never
    fails the upload (the doc stays pending for a later reconcile/retry)."""

    class _BoomTask:
        def delay(self, *args: object) -> None:
            raise RuntimeError("broker down")

    import app.tasks.document_ocr as task_mod

    monkeypatch.setattr(task_mod, "run_document_ocr", _BoomTask())
    # Must not raise.
    await CeleryOcrDispatcher().enqueue(uuid4())
