"""Workspace-root pytest config — disables the OTel SDK before any test
module imports a service's app.main, which calls setup_telemetry() at
module load time. Without this, every test run would spawn OTLP exporter
threads pointing at an otel-collector that does not exist in the test
environment, log connection errors, and slow shutdown.
"""

from __future__ import annotations

import os

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
