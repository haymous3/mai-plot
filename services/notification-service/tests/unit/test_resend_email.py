"""Resend email adapter + the provider seam (SCRUM-211).

notification-service could never send an email: it only had an SES client, and
SES has credentials in no environment we run — staging sets SES_USE_FAKE=true and
the AWS account is still outstanding. So every notification email went into an
in-process list, which is why an approved realtor never received their
registration number while auth-service's Resend verification mail arrived fine.
"""

from __future__ import annotations

import httpx
import pytest

from app.adapters.resend_email import ResendEmailClient
from app.adapters.ses_email import (
    EmailError,
    EmailMessage,
    InMemorySesClient,
    SesEmailClient,
    build_email_client,
)

_MESSAGE = EmailMessage(
    to="ada@example.com",
    subject="You're approved as a Maihomme realtor",
    html_body="<p>MH-R-000123</p>",
    text_body="MH-R-000123",
)


def _client_with(handler: httpx.MockTransport) -> ResendEmailClient:
    client = ResendEmailClient(api_key="re_test", from_email="Maihomme <noreply@maiplot.ng>")
    client._client = httpx.AsyncClient(
        base_url="https://api.resend.com",
        transport=handler,
        headers={"Authorization": "Bearer re_test"},
    )
    return client


@pytest.mark.asyncio
async def test_send_posts_the_message_to_resend() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "url": str(request.url),
                "auth": request.headers.get("authorization"),
                "body": request.read().decode(),
            }
        )
        return httpx.Response(200, json={"id": "abc"})

    await _client_with(httpx.MockTransport(handler)).send(_MESSAGE)

    assert seen[0]["url"] == "https://api.resend.com/emails"
    assert seen[0]["auth"] == "Bearer re_test"
    body = str(seen[0]["body"])
    assert "ada@example.com" in body
    # Both parts go out: a text alternative keeps the mail out of spam filters
    # that penalise HTML-only, and it is what a plain-text client shows.
    assert "MH-R-000123" in body


@pytest.mark.asyncio
async def test_a_4xx_from_resend_raises_the_shared_email_error() -> None:
    """EmailError, not a Resend-specific type: the Celery task's retry/backoff
    is written against it, so swapping providers must not change what the task
    catches."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="domain not verified")

    with pytest.raises(EmailError):
        await _client_with(httpx.MockTransport(handler)).send(_MESSAGE)


@pytest.mark.asyncio
async def test_a_transport_failure_raises_the_shared_email_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(EmailError):
        await _client_with(httpx.MockTransport(handler)).send(_MESSAGE)


@pytest.mark.asyncio
async def test_the_error_body_is_truncated() -> None:
    """A Resend error body can echo the payload back, and the payload holds the
    recipient and the message — so it must not land whole in an exception that
    gets logged."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="x" * 5000)

    with pytest.raises(EmailError) as excinfo:
        await _client_with(httpx.MockTransport(handler)).send(_MESSAGE)
    assert len(str(excinfo.value)) < 400


def test_the_factory_honours_the_provider() -> None:
    fake = build_email_client(
        use_fake=True, from_email="a@b.com", region="af-south-1", endpoint_url=""
    )
    assert isinstance(fake, InMemorySesClient)

    resend = build_email_client(
        use_fake=False,
        from_email="a@b.com",
        region="af-south-1",
        endpoint_url="",
        provider="resend",
        api_key="re_test",
    )
    assert isinstance(resend, ResendEmailClient)

    # SES stays reachable for the day the AWS account exists (§2 names it as the
    # planned provider); it is simply not the default any more.
    ses = build_email_client(
        use_fake=False,
        from_email="a@b.com",
        region="af-south-1",
        endpoint_url="",
        provider="ses",
    )
    assert isinstance(ses, SesEmailClient)


def test_the_fake_still_wins_over_any_provider() -> None:
    """use_fake is the kill switch for BOTH providers — local and CI must never
    dial out, whichever provider is configured."""
    client = build_email_client(
        use_fake=True,
        from_email="a@b.com",
        region="af-south-1",
        endpoint_url="",
        provider="resend",
        api_key="re_test",
    )
    assert isinstance(client, InMemorySesClient)


@pytest.mark.asyncio
async def test_a_rejection_does_not_log_success(caplog: pytest.LogCaptureFixture) -> None:
    """The status check runs BEFORE the success log.

    Found live: the first cut logged `resend.notification.ok` and *then* raised,
    so a run where Resend 403'd every message (unverified sender domain) filled
    the log with "ok" while nothing was delivered. A log that says the opposite
    of what happened is worse than no log — it sent me looking in the wrong
    place.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="The maihomme.com domain is not verified")

    with caplog.at_level("INFO"), pytest.raises(EmailError):
        await _client_with(httpx.MockTransport(handler)).send(_MESSAGE)

    messages = [record.message for record in caplog.records]
    assert "resend.notification.ok" not in messages
    assert "resend.notification.rejected" in messages
