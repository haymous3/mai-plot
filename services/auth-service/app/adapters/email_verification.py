"""Provider-agnostic verification-email adapter (SCRUM-152).

Mirrors the Termii adapter's shape (Protocol + real client + in-memory
fake + factory), but for transactional email:

  * EmailVerificationSender — the Protocol every call site depends on.
  * ResendClient — real adapter over Resend's REST API (the default
    provider). httpx handles pooling; a send failure is one
    EmailDeliveryError.
  * InMemoryEmailClient — in-process fake; captures sent links so tests
    assert what was sent without hitting the network.

WHY provider-agnostic: CLAUDE.md §9 keeps user PII in af-south-1, which
AWS SES satisfies and a US provider does not. Resend is the chosen V1
provider (product owner accepted the residency trade-off), but the
factory below is the single seam where an SesClient slots in later —
flip `email_provider` in settings, no call-site changes.

The verification email is a fixed template, so this adapter owns the
subject/body — call sites pass only the recipient and the link.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_SUBJECT = "Verify your Maiplot email address"


def _render_bodies(verify_url: str) -> tuple[str, str]:
    """Return (html_body, text_body) for a verification email."""
    text_body = (
        "Welcome to Maiplot.\n\n"
        "Confirm your email address by opening this link:\n"
        f"{verify_url}\n\n"
        "The link expires shortly and can only be used once. "
        "If you did not create a Maiplot account, you can ignore this email."
    )
    html_body = (
        "<p>Welcome to Maiplot.</p>"
        "<p>Confirm your email address by clicking the button below:</p>"
        f'<p><a href="{verify_url}" '
        'style="background:#0b7a4b;color:#fff;padding:12px 20px;'
        'border-radius:6px;text-decoration:none">Verify email</a></p>'
        f'<p>Or paste this link into your browser:<br><a href="{verify_url}">{verify_url}</a></p>'
        "<p>The link expires shortly and can only be used once. "
        "If you did not create a Maiplot account, you can ignore this email.</p>"
    )
    return html_body, text_body


@dataclass(frozen=True)
class VerificationEmail:
    to: str
    verify_url: str


class EmailDeliveryError(RuntimeError):
    """Raised when the provider rejects or fails to accept the message."""


class EmailVerificationSender(Protocol):
    async def send_verification(
        self, email: VerificationEmail
    ) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryEmailClient:
    """Test double — captures sent verification emails in-process.

    Construct fresh per test (the client is injected) so there is no global
    state to clear between tests.
    """

    sent: list[VerificationEmail] = field(default_factory=list)
    fail_next: bool = False

    async def send_verification(self, email: VerificationEmail) -> None:
        if self.fail_next:
            self.fail_next = False
            raise EmailDeliveryError("simulated email delivery failure")
        self.sent.append(email)


class ResendClient:
    """Sends via Resend's POST /emails endpoint. One client per process."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._from_address = from_address
        self._client = httpx.AsyncClient(
            base_url="https://api.resend.com",
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def send_verification(self, email: VerificationEmail) -> None:
        html_body, text_body = _render_bodies(email.verify_url)
        payload = {
            "from": self._from_address,
            "to": [email.to],
            "subject": _SUBJECT,
            "html": html_body,
            "text": text_body,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post("/emails", json=payload)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            # Only the domain part is logged — never the full recipient address.
            logger.error(
                "resend.send.failed",
                extra={"to_domain": _domain(email.to), "duration_ms": duration_ms},
            )
            raise EmailDeliveryError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "resend.send.ok",
            extra={
                "to_domain": _domain(email.to),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        if response.status_code >= 400:
            raise EmailDeliveryError(
                f"resend returned {response.status_code}: {response.text[:200]}"
            )

    async def aclose(self) -> None:
        await self._client.aclose()


def _domain(address: str) -> str:
    """The domain part of an email, for safe logging (no local part)."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


def build_email_verification_client(
    *,
    provider: str,
    use_fake: bool,
    api_key: str,
    from_address: str,
    timeout_seconds: float,
) -> EmailVerificationSender:
    """Factory — in-memory fake for local/CI, else the configured provider.

    Adding SES later is a new branch here plus an SesClient class; no call
    site changes (that is the point of the Protocol).
    """
    if use_fake:
        return InMemoryEmailClient()
    if provider == "resend":
        return ResendClient(
            api_key=api_key,
            from_address=from_address,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unsupported email provider: {provider!r}")
