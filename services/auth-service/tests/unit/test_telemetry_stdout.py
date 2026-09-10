"""Application logs must reach stdout (SCRUM-220).

Before this, the root logger carried ONLY the OTLP handler, so on any host
without a collector — Railway, or a bare `docker run` — every application log
line was formatted and discarded. These tests pin the two properties that
made a live 502 undiagnosable: that a line is emitted at all, and that the
`extra` payload survives, since that is where every diagnostic value lives.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable
from typing import Any

import pytest

from app.telemetry import _log_level, _StdoutJsonFormatter


def _emit(record_factory: Callable[[logging.Logger], None]) -> dict[str, Any]:
    """Format one record through the real formatter and parse it back."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_StdoutJsonFormatter())
    logger = logging.getLogger(f"test.{id(record_factory)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    record_factory(logger)
    parsed: dict[str, Any] = json.loads(stream.getvalue().strip())
    return parsed


def test_extra_fields_survive_to_stdout() -> None:
    """The whole point. `%(message)s` drops `extra` silently, which is how a
    provider's exact status code got thrown away while we probed the vendor
    by hand to find out what it was."""
    payload = _emit(
        lambda log: log.error(
            "nin.provider.error_status",
            extra={"status_code": 402, "duration_ms": 12.5},
        )
    )

    assert payload["event"] == "nin.provider.error_status"
    assert payload["status_code"] == 402
    assert payload["duration_ms"] == 12.5
    assert payload["level"] == "error"


def test_unserialisable_extra_cannot_break_the_log_call() -> None:
    """A UUID or datetime in `extra` must not turn logging into a TypeError
    inside the request it was meant to describe."""
    from uuid import uuid4

    user_id = uuid4()
    payload = _emit(lambda log: log.info("nin.verify.ok", extra={"user_id": user_id}))

    assert payload["user_id"] == str(user_id)


def test_structlog_json_is_passed_through_not_nested() -> None:
    """structlog renders its event as a JSON object before it reaches stdlib.
    Re-encoding it would bury the real fields inside an escaped string."""
    payload = _emit(lambda log: log.info('{"event": "telemetry_initialized", "service": "auth"}'))

    assert payload == {"event": "telemetry_initialized", "service": "auth"}


def test_a_plain_message_that_merely_starts_with_a_brace_is_not_mistaken_for_json() -> None:
    payload = _emit(lambda log: log.info("{not json after all"))

    assert payload["event"] == "{not json after all"


def test_exception_info_is_included() -> None:
    def raise_and_log(log: logging.Logger) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            log.exception("something.failed")

    payload = _emit(raise_and_log)

    assert payload["event"] == "something.failed"
    assert "ValueError: boom" in payload["exc_info"]


def test_log_level_reads_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    assert _log_level() == logging.WARNING


def test_log_level_strips_an_inline_dotenv_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value carried in from a .env file keeps its inline comment — the trap
    that broke the ENV == "local" gate in SCRUM-179."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG  # verbose in staging")
    assert _log_level() == logging.DEBUG


def test_log_level_falls_back_to_info_on_nonsense(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    assert _log_level() == logging.INFO


def test_log_level_defaults_to_info_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert _log_level() == logging.INFO


def test_configure_stdout_logging_attaches_a_root_handler() -> None:
    from app.telemetry import _StdoutHandler, configure_stdout_logging

    root = logging.getLogger()
    original = list(root.handlers)
    try:
        configure_stdout_logging()
        assert any(isinstance(h, _StdoutHandler) for h in root.handlers)
    finally:
        root.handlers = original


def test_configure_stdout_logging_is_idempotent() -> None:
    """Hot reload and a double import must not double every log line."""
    from app.telemetry import _StdoutHandler, configure_stdout_logging

    root = logging.getLogger()
    original = list(root.handlers)
    try:
        configure_stdout_logging()
        configure_stdout_logging()
        configure_stdout_logging()
        assert sum(isinstance(h, _StdoutHandler) for h in root.handlers) == 1
    finally:
        root.handlers = original


def test_configure_stdout_logging_leaves_foreign_handlers_alone() -> None:
    from app.telemetry import configure_stdout_logging

    root = logging.getLogger()
    original = list(root.handlers)
    sentinel = logging.NullHandler()
    try:
        root.addHandler(sentinel)
        configure_stdout_logging()
        assert sentinel in root.handlers
    finally:
        root.handlers = original


def test_uvicorn_access_records_are_filtered_off_stdout() -> None:
    """uvicorn prints these itself; without the filter every request would be
    logged to stdout twice."""
    from app.telemetry import _StdoutHandler, configure_stdout_logging

    root = logging.getLogger()
    original = list(root.handlers)
    try:
        configure_stdout_logging()
        handler = next(h for h in root.handlers if isinstance(h, _StdoutHandler))
        access = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "GET / 200", None, None)
        app_record = logging.LogRecord(
            "app.adapters.nin", logging.INFO, "", 0, "nin.provider.ok", None, None
        )
        # handler.filter() applies every registered filter, and copes with a
        # plain callable as well as a Filter instance.
        assert not handler.filter(access)
        assert handler.filter(app_record)
    finally:
        root.handlers = original


def test_stdout_logging_survives_the_otel_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """OTEL_SDK_DISABLED turns off OpenTelemetry, not logging. Moving the
    stdout wiring after that early return is the one edit that would silently
    undo this ticket, so it is pinned here."""
    from fastapi import FastAPI

    from app.telemetry import _StdoutHandler, setup_telemetry

    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    root = logging.getLogger()
    original = list(root.handlers)
    try:
        root.handlers = []
        setup_telemetry("auth-service", FastAPI())
        assert any(isinstance(h, _StdoutHandler) for h in root.handlers)
    finally:
        root.handlers = original
