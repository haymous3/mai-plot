"""Sentry init smoke test — exercises both branches of _init_sentry so
Codecov patch coverage stays above threshold without us needing a real
SENTRY_DSN. Same test is distributed to every service because each
service has its own copy of app/telemetry.py that Codecov measures
separately.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from app.telemetry import _init_sentry


def test_init_sentry_noop_when_dsn_empty() -> None:
    with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
        _init_sentry("test-service", "test")


def test_init_sentry_noop_when_dsn_missing() -> None:
    env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    with patch.dict(os.environ, env_without_dsn, clear=True):
        _init_sentry("test-service", "test")


def test_init_sentry_initialises_when_dsn_present() -> None:
    """Exercises the DSN-present branch by mocking sentry_sdk.init so we
    don't open a real Sentry connection from CI."""
    fake_dsn = "https://public@example.ingest.sentry.io/12345"
    with (
        patch.dict(os.environ, {"SENTRY_DSN": fake_dsn}),
        patch("sentry_sdk.init") as mock_init,
    ):
        _init_sentry("auth-service", "test")

    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == fake_dsn
    assert kwargs["server_name"] == "auth-service"
    assert kwargs["environment"] == "test"
    assert kwargs["traces_sample_rate"] == 0.0
    assert kwargs["send_default_pii"] is False
