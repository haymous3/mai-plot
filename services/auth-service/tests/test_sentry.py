"""Sentry init smoke test — confirms _init_sentry is a no-op without DSN.

We don't import Sentry-internal state; we just patch the env, call the
function, and assert no exception. The real Sentry call paths are
exercised in staging once a DSN is set.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from app.telemetry import _init_sentry


def test_init_sentry_noop_when_dsn_absent() -> None:
    with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
        _init_sentry("auth-service", "test")


def test_init_sentry_noop_when_dsn_missing() -> None:
    env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    with patch.dict(os.environ, env_without_dsn, clear=True):
        _init_sentry("auth-service", "test")
