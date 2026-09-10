"""OpenTelemetry + structlog wiring shared across every Maiplot service.

Same file copied verbatim into each service. Promote to a `_shared`
workspace member when the duplication actually hurts; for now CLAUDE.md
keeps services independent.

What this does at startup:
  * Builds an OTel Resource with service.name + deployment.environment.
  * Sends spans to the OTel collector via OTLP gRPC at $OTEL_EXPORTER_OTLP_ENDPOINT.
  * Sends OTLP metrics on the same channel (auto-instrumentation emits
    http.server.request.duration etc.).
  * Sends OTLP logs on the same channel — the collector fans them out to
    Loki, and each record carries trace_id / span_id taken from the
    active span via the stdlib logging instrumentation.
  * Configures structlog to use that stdlib logging path so every
    structlog.get_logger() call inherits trace correlation for free.
  * Auto-instruments the FastAPI app + asyncpg + httpx so every request
    and outbound call gets a span without per-handler code changes.

Set OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 in the
container env. The fall-back lets a developer run a single service on
the host without the full compose stack.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

DEFAULT_OTLP_ENDPOINT = "http://otel-collector:4317"

# Attributes every LogRecord already carries. Anything NOT in here came from a
# caller's `extra={...}` (or from OTel's LoggingInstrumentor, which injects
# otelTraceID/otelSpanID) and is exactly the payload worth printing.
_STD_RECORD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {
    "asctime",
    "message",
    "taskName",
}

# uvicorn installs its own stdout handler for these and we flip propagate=True
# below so their records still reach the OTLP exporter. Without this filter the
# stdout handler would print every access line a second time.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marker subclass so the hot-reload cleanup above can drop exactly the
    handler this module added, without touching one a test or a host process
    attached for its own reasons."""


class _StdoutJsonFormatter(logging.Formatter):
    """Render a record as one JSON line, INCLUDING its `extra` fields.

    The default `%(message)s` formatting silently drops `extra`, which is
    where every diagnostic value in this codebase lives — status codes,
    durations, ids. A log line saying only "nin.provider.error_status" with
    the status code thrown away is why SCRUM-220 exists.
    """

    def format(self, record: logging.LogRecord) -> str:
        rendered = record.getMessage()
        # structlog routes through stdlib logging with the event already
        # rendered as a JSON object. Pass it straight through rather than
        # nesting an encoded string inside another object.
        if rendered.startswith("{"):
            try:
                if isinstance(json.loads(rendered), dict):
                    return rendered
            except ValueError:
                pass

        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": rendered,
        }
        for key, value in record.__dict__.items():
            if key not in _STD_RECORD_FIELDS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # default=str so a UUID or datetime in `extra` can never turn a log
        # line into a TypeError inside the logging call itself.
        return json.dumps(payload, default=str)


def _log_level() -> int:
    """LOG_LEVEL from env, defaulting to INFO.

    `.split("#")` because a value carried in from a .env file keeps its inline
    comment — the same trap that broke the `ENV == "local"` gate in SCRUM-179.
    """
    raw = os.environ.get("LOG_LEVEL", "INFO").split("#", 1)[0].strip().upper()
    level = logging.getLevelNamesMapping().get(raw)
    return level if isinstance(level, int) else logging.INFO


def configure_stdout_logging() -> None:
    """Attach the JSON stdout handler to the root logger.

    ⚠️ STDOUT IS NOT OPTIONAL (SCRUM-220). Until this existed the root logger
    carried ONLY the OTLP handler, so on any host without a collector running —
    Railway, and every `docker run` of a single service — every application log
    line was built, formatted and thrown away. Only uvicorn's access lines
    appeared, because uvicorn installs its own handler. That made a live 502
    undiagnosable from the platform's own log view: the NIN adapter was logging
    the provider's exact status code and nobody could read it.

    ⚠️ Called BEFORE the OTEL_SDK_DISABLED check in setup_telemetry, and
    deliberately so. That flag turns off OpenTelemetry, not logging; a service
    started with it set still has to be debuggable. Putting this after the
    early return is the one edit that would silently undo the whole ticket.
    """
    level = _log_level()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Idempotent: drop only the handler we added, never one a test or a host
    # process attached for its own reasons.
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, _StdoutHandler)]

    handler = _StdoutHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(_StdoutJsonFormatter())
    # uvicorn installs its own stdout handler for these and we flip
    # propagate=True below so their records still reach OTLP. Without this
    # filter every access line would print twice.
    handler.addFilter(lambda record: not record.name.startswith(_UVICORN_LOGGERS))
    root_logger.addHandler(handler)


def setup_telemetry(service_name: str, app: FastAPI) -> None:
    # Logging first, and outside the kill switch below — see the docstring.
    configure_stdout_logging()

    # OTEL_SDK_DISABLED is the canonical OTel kill switch (used in tests
    # and one-off scripts that import the FastAPI app without a running
    # collector). Bail out before we attach any exporters or instrument
    # the app — re-instrumenting on a hot-reload also no-ops cleanly.
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("true", "1", "yes"):
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
    environment = os.environ.get("ENV", "local")

    # Sentry is initialised before any OTel wiring so an exception during
    # OTel setup itself still surfaces in Sentry. It's a no-op in dev
    # without a DSN, so this adds zero overhead locally.
    _init_sentry(service_name, environment)

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "maiplot",
            "deployment.environment": environment,
        }
    )

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=15_000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    # Logs — OTLP path. The LoggingHandler attached to the root logger
    # below shovels every stdlib logging record through the OTel pipeline.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)

    # Inject trace_id / span_id into every stdlib log record so the line
    # carries the correlation key downstream backends can index.
    LoggingInstrumentor().instrument(set_logging_format=False)

    level = _log_level()
    root_logger = logging.getLogger()
    # Avoid duplicates if setup runs twice (e.g. hot reload). The stdout
    # handler is managed by configure_stdout_logging() and left alone here.
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, LoggingHandler)]
    root_logger.addHandler(LoggingHandler(level=level, logger_provider=logger_provider))

    # structlog — emit JSON, route through stdlib logging so the same
    # records flow into the OTLP handler above.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _attach_trace_context,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Auto-instrumentation: FastAPI is always wired (every service is a
    # FastAPI app). The asyncpg and httpx instrumentations import the
    # underlying library at module load, so we only attach them when the
    # service actually depends on those libraries — keeps the dev image
    # of services that don't make DB or outbound HTTP calls smaller.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    _instrument_optional("asyncpg", tracer_provider)
    _instrument_optional("httpx", tracer_provider)

    # uvicorn configures its own `uvicorn` and `uvicorn.access` loggers
    # with propagate=False, so by default their records never reach the
    # root logger and the OTLP log handler attached above. Flip propagate
    # back on so access logs land in Loki alongside the app's own logs.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).propagate = True

    # Emit one startup log so Loki has at least one record per service
    # start even before any request lands. Demonstrates structured JSON
    # output and the trace_id field shape.
    structlog.get_logger().info(
        "telemetry_initialized",
        service=service_name,
        environment=environment,
        otlp_endpoint=endpoint,
    )


def _init_sentry(service_name: str, environment: str) -> None:
    """Initialise Sentry error capture if SENTRY_DSN is set in env.

    Tracing stays with OTel (traces_sample_rate=0) — Sentry handles
    error capture only, no double ingestion. server_name is the service
    name so the Sentry UI can split error streams per service even
    though all services share one DSN."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        server_name=service_name,
        traces_sample_rate=0.0,
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )


def _instrument_optional(library: str, tracer_provider: TracerProvider) -> None:
    """Activate an OTel auto-instrumentation only if its target library
    is importable. Silently no-ops otherwise."""
    try:
        __import__(library)
    except ImportError:
        return

    if library == "asyncpg":
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        AsyncPGInstrumentor().instrument(tracer_provider=tracer_provider)  # type: ignore[no-untyped-call]
    elif library == "httpx":
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)


def _attach_trace_context(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor — copies trace_id/span_id from the active span
    into the rendered JSON record. Mirrors what LoggingInstrumentor does
    for stdlib calls so structlog-direct log lines also carry the keys."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
        event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    return event_dict
