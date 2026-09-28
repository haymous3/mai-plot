"""Provider-agnostic verification-email adapter (SCRUM-152).

Mirrors the Twilio adapter's shape (Protocol + real client + in-memory
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

Each email is a fixed template, so this adapter owns every subject/body —
call sites pass only the recipient and the link. Two templates live here:
account verification (SCRUM-152), password reset (SCRUM-191) and the
"a new account was added to your sign-in" notice (SCRUM-236). They are
separate methods rather than one `send(subject, body)` so a call site cannot
send the wrong copy, and so the in-memory fake can assert which KIND of mail
a flow sent.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_SUBJECT = "Verify your Maihomme email address"


def _render_bodies(verify_url: str) -> tuple[str, str]:
    """Return (html_body, text_body) for a verification email."""
    text_body = (
        "Welcome to Maihomme.\n\n"
        "Confirm your email address by opening this link:\n"
        f"{verify_url}\n\n"
        "The link expires shortly and can only be used once. "
        "If you did not create a Maihomme account, you can ignore this email."
    )
    html_body = (
        "<p>Welcome to Maihomme.</p>"
        "<p>Confirm your email address by clicking the button below:</p>"
        f'<p><a href="{verify_url}" '
        'style="background:#0b7a4b;color:#fff;padding:12px 20px;'
        'border-radius:6px;text-decoration:none">Verify email</a></p>'
        f'<p>Or paste this link into your browser:<br><a href="{verify_url}">{verify_url}</a></p>'
        "<p>The link expires shortly and can only be used once. "
        "If you did not create a Maihomme account, you can ignore this email.</p>"
    )
    return html_body, text_body


@dataclass(frozen=True)
class VerificationEmail:
    to: str
    verify_url: str


_RESET_SUBJECT = "Reset your Maihomme password"


def _render_reset_bodies(reset_url: str) -> tuple[str, str]:
    """Return (html_body, text_body) for a password-reset email.

    The copy must state that an unrequested reset is harmless and changes
    nothing - this mail is the one an attacker can trigger for someone else's
    address, so it should never read as an alarm or imply an account change
    has already happened.
    """
    text_body = (
        "We received a request to reset your Maihomme password.\n\n"
        "Choose a new password here:\n"
        f"{reset_url}\n\n"
        "The link expires shortly and can only be used once. "
        "If you did not request this, you can ignore this email - "
        "your password has not been changed."
    )
    html_body = (
        "<p>We received a request to reset your Maihomme password.</p>"
        "<p>Choose a new password by clicking the button below:</p>"
        f'<p><a href="{reset_url}" '
        'style="background:#0b7a4b;color:#fff;padding:12px 20px;'
        'border-radius:6px;text-decoration:none">Reset password</a></p>'
        f'<p>Or paste this link into your browser:<br><a href="{reset_url}">{reset_url}</a></p>'
        "<p>The link expires shortly and can only be used once. "
        "If you did not request this, you can ignore this email - "
        "your password has not been changed.</p>"
    )
    return html_body, text_body


@dataclass(frozen=True)
class PasswordResetEmail:
    to: str
    reset_url: str


_ROLE_LABELS = {"buyer": "buyer", "seller": "seller"}


def _render_role_added_bodies(role: str) -> tuple[str, str]:
    """Return (html_body, text_body) for the role-added notice (SCRUM-236).

    Sent AFTER the fact, to the address on the login — the person was signed
    in, so this is a receipt, not a confirmation. It has to read clearly to
    someone who did NOT do it, because that is the one reader it protects.
    No link: a notice that invites a click trains people to click notices.
    """
    label = _ROLE_LABELS.get(role, role)
    text_body = (
        f"Your Maihomme sign-in was just used to create a {label} account.\n\n"
        f"You can now switch between your accounts from the account menu, using "
        f"the same email and password.\n\n"
        "If this wasn't you, change your password straight away and contact "
        "Maihomme support."
    )
    html_body = (
        f"<p>Your Maihomme sign-in was just used to create a <strong>{label}</strong> "
        "account.</p>"
        "<p>You can now switch between your accounts from the account menu, using "
        "the same email and password.</p>"
        "<p>If this wasn't you, change your password straight away and contact "
        "Maihomme support.</p>"
    )
    return html_body, text_body


@dataclass(frozen=True)
class RoleAddedEmail:
    to: str
    role: str


class EmailDeliveryError(RuntimeError):
    """Raised when the provider rejects or fails to accept the message."""


class EmailVerificationSender(Protocol):
    async def send_verification(
        self, email: VerificationEmail
    ) -> None:  # pragma: no cover - protocol
        ...

    async def send_password_reset(
        self, email: PasswordResetEmail
    ) -> None:  # pragma: no cover - protocol
        ...

    async def send_role_added(self, email: RoleAddedEmail) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class InMemoryEmailClient:
    """Test double — captures sent verification emails in-process.

    Construct fresh per test (the client is injected) so there is no global
    state to clear between tests.
    """

    sent: list[VerificationEmail] = field(default_factory=list)
    sent_password_resets: list[PasswordResetEmail] = field(default_factory=list)
    sent_role_added: list[RoleAddedEmail] = field(default_factory=list)
    fail_next: bool = False

    async def send_verification(self, email: VerificationEmail) -> None:
        if self.fail_next:
            self.fail_next = False
            raise EmailDeliveryError("simulated email delivery failure")
        self.sent.append(email)

    async def send_password_reset(self, email: PasswordResetEmail) -> None:
        # Kept in its own list so a test asserting "a reset was sent" cannot
        # be satisfied by a verification email, and vice versa.
        if self.fail_next:
            self.fail_next = False
            raise EmailDeliveryError("simulated email delivery failure")
        self.sent_password_resets.append(email)

    async def send_role_added(self, email: RoleAddedEmail) -> None:
        if self.fail_next:
            self.fail_next = False
            raise EmailDeliveryError("simulated email delivery failure")
        self.sent_role_added.append(email)


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
        await self._send(
            to=email.to, subject=_SUBJECT, html=html_body, text=text_body, kind="verification"
        )

    async def send_password_reset(self, email: PasswordResetEmail) -> None:
        html_body, text_body = _render_reset_bodies(email.reset_url)
        await self._send(
            to=email.to,
            subject=_RESET_SUBJECT,
            html=html_body,
            text=text_body,
            kind="password_reset",
        )

    async def send_role_added(self, email: RoleAddedEmail) -> None:
        html_body, text_body = _render_role_added_bodies(email.role)
        label = _ROLE_LABELS.get(email.role, email.role)
        await self._send(
            to=email.to,
            subject=f"A {label} account was added to your Maihomme sign-in",
            html=html_body,
            text=text_body,
            kind="role_added",
        )

    async def _send(self, *, to: str, subject: str, html: str, text: str, kind: str) -> None:
        payload = {
            "from": self._from_address,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post("/emails", json=payload)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            # Only the domain part is logged — never the full recipient address.
            logger.error(
                "resend.send.failed",
                extra={"to_domain": _domain(to), "kind": kind, "duration_ms": duration_ms},
            )
            raise EmailDeliveryError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "resend.send.ok",
            extra={
                "to_domain": _domain(to),
                "kind": kind,
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
