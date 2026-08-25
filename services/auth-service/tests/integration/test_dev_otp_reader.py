"""GET /dev/otp/latest — the local-only OTP reader.

Most of these tests are about what the endpoint REFUSES to do. It exists to
hand a developer the plaintext OTP that the fake adapter swallowed, which is
useful locally and would be a serious hole anywhere else, so the gates matter
more than the happy path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from app.config import Settings
from app.routes.dev import dev_routes_enabled
from tests.integration.conftest import extract_otp_code, register_only

_PHONE_LOCAL = "08012345678"
_PHONE = "+2348012345678"
_EMAIL = "buyer@example.com"


# --- the gate itself, in isolation -----------------------------------------


@pytest.mark.parametrize(
    ("env", "use_fake", "expected"),
    [
        ("local", True, True),
        ("local", False, False),
        ("staging", True, False),
        ("staging", False, False),
        ("production", True, False),
        ("production", False, False),
        # Whitespace is dotenv formatting noise, not a different value, so it
        # is stripped and still enables.
        ("local ", True, True),
        # Near-misses that are genuinely DIFFERENT values must not enable —
        # case included, since a wrong case is a typo, not formatting.
        ("Local", True, False),
        ("localhost", True, False),
        ("", True, False),
    ],
)
def test_dev_routes_enabled_only_for_exactly_local_and_fake(
    env: str, use_fake: bool, expected: bool
) -> None:
    settings = Settings(env=env, twilio_use_fake=use_fake)
    assert dev_routes_enabled(settings) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("local   # local | staging | production", True),
        ("  local  ", True),
        ("staging  # set by maiplot-shared", False),
        ("production#prod", False),
    ],
)
def test_inline_dotenv_comments_are_stripped(raw: str, expected: bool) -> None:
    """pydantic-settings does not strip inline `# comments`, so `.env`'s
    `ENV=local   # local | staging | production` arrived as the whole line and
    silently disabled these routes. Settings normalises it now. Stripping only
    ever narrows a value, so it cannot turn a non-local env into "local"."""
    assert dev_routes_enabled(Settings(env=raw, twilio_use_fake=True)) is expected


def test_staging_env_group_value_does_not_enable_dev_routes() -> None:
    """render.yaml's maiplot-shared sets ENV=staging. Pin that exact value so a
    future rename cannot quietly switch these routes on in staging."""
    assert dev_routes_enabled(Settings(env="staging", twilio_use_fake=True)) is False


# --- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_the_code_that_was_sent(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    expected = extract_otp_code(sms_fake.sent[-1].message)

    resp = await http_client.get("/dev/otp/latest")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == expected
    assert body["phone"] == _PHONE
    assert body["total_sent"] == 1


@pytest.mark.asyncio
async def test_code_actually_verifies(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The whole point: a developer can now complete the flow locally."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)

    code = (await http_client.get("/dev/otp/latest")).json()["code"]
    verified = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": code, "purpose": "registration"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["user"]["verified_status"] == "phone_verified"


@pytest.mark.asyncio
async def test_filters_by_phone_in_either_format(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    await register_only(http_client, phone="08087654321", role="buyer", email="other@example.com")
    first = extract_otp_code(sms_fake.sent[0].message)

    for form in (_PHONE_LOCAL, _PHONE):
        resp = await http_client.get("/dev/otp/latest", params={"phone": form})
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == first
        assert resp.json()["phone"] == _PHONE


@pytest.mark.asyncio
async def test_unknown_phone_returns_404(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get("/dev/otp/latest", params={"phone": "08099999999"})
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NO_OTP_SENT"


@pytest.mark.asyncio
async def test_invalid_phone_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.get("/dev/otp/latest", params={"phone": "not-a-number"})
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


# --- refusals ---------------------------------------------------------------


@pytest_asyncio.fixture
async def staging_settings() -> AsyncIterator[None]:
    """Pretend the process booted with ENV=staging, without re-importing the app."""
    from app.config import get_settings
    from app.main import app

    real = get_settings()
    staged = real.model_copy(update={"env": "staging"})
    app.dependency_overrides[get_settings] = lambda: staged
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.mark.asyncio
async def test_handler_refuses_when_env_is_not_local(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    staging_settings: None,
    http_client: AsyncClient,
) -> None:
    """Belt-and-braces gate 3: even with the router registered (as it is in this
    test process) and a code sitting in the fake, a non-local env gets nothing —
    and gets a bare 404 that doesn't confirm the endpoint exists."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    assert sms_fake.sent, "precondition: the fake really is holding a code"

    resp = await http_client.get("/dev/otp/latest")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"
    # The code must not appear anywhere in the response.
    assert extract_otp_code(sms_fake.sent[-1].message) not in resp.text


@pytest_asyncio.fixture
async def real_sms_client_bound() -> AsyncIterator[None]:
    """Bind something that is not the in-memory fake."""
    from app.dependencies import get_sms_client
    from app.main import app

    class _NotTheFake:
        async def send_sms(self, phone: str, message: str) -> None:  # pragma: no cover
            raise AssertionError("must not be called")

    app.dependency_overrides[get_sms_client] = lambda: _NotTheFake()
    yield
    app.dependency_overrides.pop(get_sms_client, None)


@pytest.mark.asyncio
async def test_handler_refuses_when_a_real_client_is_bound(
    clean_auth_tables: None,
    disable_rate_limit: None,
    real_sms_client_bound: None,
    http_client: AsyncClient,
) -> None:
    """Gate 4: this must never become a way to read traffic that really went to
    a handset, however the app is configured."""
    resp = await http_client.get("/dev/otp/latest")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"


def test_dev_path_is_not_routed_by_kong() -> None:
    """Gate 1: Kong must not proxy /dev. auth-service is a private service, so
    Kong's path list is what makes this unreachable from outside — this test
    fails loudly if someone ever adds a /dev route to the gateway."""
    from pathlib import Path

    kong = Path(__file__).resolve().parents[4] / "infra" / "kong" / "kong.yml"
    assert kong.is_file(), f"kong.yml not found at {kong}"
    routed = [
        line.strip().lstrip("- ").strip()
        for line in kong.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- /")
    ]
    assert routed, "precondition: parsed at least one Kong path"
    offenders = [p for p in routed if p == "/dev" or p.startswith("/dev/")]
    assert not offenders, f"Kong must not route /dev — found {offenders}"
