"""AWS SES adapter — transactional email (SCRUM-81).

Three pieces, mirroring the Termii / Web Push adapters:
  * EmailClient — Protocol every callable site depends on.
  * SesEmailClient — real adapter over boto3 SES `send_email`. boto3 is
    synchronous, so the blocking call runs in a worker thread.
  * InMemorySesClient — in-process fake; captures sent messages so tests assert
    what was sent without touching AWS.

Production binds the real client via SES_USE_FAKE=false + a verified
ses_from_email; CI/local get the fake by default. Any send failure is a single
EmailError (transient — the Celery task retries); per-recipient bounce/complaint
handling is an SES-side concern wired up separately.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str


class EmailError(RuntimeError):
    """A transient email send failure — safe to retry."""


class EmailClient(Protocol):
    async def send(self, message: EmailMessage) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class InMemorySesClient:
    """Test double — captures sent messages in-process."""

    sent: list[EmailMessage] = field(default_factory=list)
    fail_next: bool = False

    async def send(self, message: EmailMessage) -> None:
        if self.fail_next:
            self.fail_next = False
            raise EmailError("simulated SES failure")
        self.sent.append(message)


class SesEmailClient:
    """Sends via AWS SES `send_email`. One client per process."""

    def __init__(self, *, from_email: str, region: str, endpoint_url: str | None = None) -> None:
        import boto3

        self._from_email = from_email
        self._client = boto3.client("ses", region_name=region, endpoint_url=endpoint_url or None)

    async def send(self, message: EmailMessage) -> None:
        started = time.perf_counter()
        try:
            await asyncio.to_thread(
                self._client.send_email,
                Source=self._from_email,
                Destination={"ToAddresses": [message.to]},
                Message={
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": message.html_body, "Charset": "UTF-8"},
                        "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                    },
                },
            )
        except Exception as exc:  # boto3 ClientError/BotoCoreError
            duration_ms = (time.perf_counter() - started) * 1000
            # Recipient is hashed-by-suffix only — no full address in the log.
            logger.error(
                "ses.send.failed",
                extra={"to_suffix": message.to[-12:], "duration_ms": duration_ms},
            )
            raise EmailError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "ses.send.ok", extra={"to_suffix": message.to[-12:], "duration_ms": duration_ms}
        )


def build_email_client(
    *,
    use_fake: bool,
    from_email: str,
    region: str,
    endpoint_url: str,
) -> EmailClient:
    """Factory — in-memory fake for local/CI, real SES client in production."""
    if use_fake:
        return InMemorySesClient()
    return SesEmailClient(from_email=from_email, region=region, endpoint_url=endpoint_url)
