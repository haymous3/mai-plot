"""Workspace-root pytest config.

Two responsibilities, both done before any test module imports a
service's app.main:

  1. Disable the OTel SDK so setup_telemetry() is a no-op at module
     load (would otherwise spawn OTLP exporter threads pointing at a
     collector that does not exist in the test environment).
  2. Source .env if present so local pytest picks up overrides like
     POSTGRES_HOST_PORT (this dev machine remaps it to 5434 because
     5432 is taken by another local Postgres). CI runs without .env
     and gets the defaults baked into the per-service conftest.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("OTEL_SDK_DISABLED", "true")

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
