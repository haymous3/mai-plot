"""Resend adapter — transactional email for notifications (SCRUM-211).

Why this exists next to ses_email.py
------------------------------------
notification-service has only ever had an SES client, and SES has no credentials
in any environment we run: staging sets `SES_USE_FAKE=true`, and the real AWS
account is still an M0 straggler. So every notification email — realtor approval,
PoA decision, loan decision, offer received — went to an in-process list and
nobody ever received one. Meanwhile auth-service's verification emails arrive
fine, because auth-service sends through **Resend**.

This is that same provider, in this service. CLAUDE.md §2 names Resend as the V1
email provider with SES "planned", so the SES client stays exactly where it is,
behind the `email_provider` switch, ready for the day AWS exists.

⚠️ §9: Resend's `maiplot.ng` domain is in eu-west-1, so notification email leaves
af-south-1 — the same documented, product-owner-accepted trade-off already made
for verification email. It is recorded here so the next person does not discover
it by surprise.

Deliberately mirrors auth-service's ResendClient rather than sharing it: services
are independent deployables with their own dependency sets, and a shared library
is a coupling this codebase has consistently declined.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.adapters.ses_email import EmailError, EmailMessage

logger = logging.getLogger(__name__)


def _domain(address: str) -> str:
    """The domain part of an email, for safe logging (never the local part)."""
    _, _, domain = address.rpartition("@")
    return domain or "?"


class ResendEmailClient:
    """Sends via Resend's POST /emails. One client per process.

    Raises the SAME `EmailError` the SES client raises, so the Celery task's
    retry/backoff logic is untouched by which provider is bound.
    """

    def __init__(
        self,
        *,
        api_key: str,
        from_email: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._from_email = from_email
        self._client = httpx.AsyncClient(
            base_url="https://api.resend.com",
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def send(self, message: EmailMessage) -> None:
        payload = {
            "from": self._from_email,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post("/emails", json=payload)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            # Domain only — a recipient address is PII and must not reach a log.
            logger.error(
                "resend.notification.failed",
                extra={"to_domain": _domain(message.to), "duration_ms": duration_ms},
            )
            raise EmailError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            # Checked BEFORE the success log, not after. Logging "ok" and then
            # raising is how a live run showed `resend.notification.ok` on every
            # line while nothing was delivered — an unverified sender domain
            # 403s, and the log said the opposite. (auth-service's adapter has
            # the same ordering; worth fixing there too.)
            logger.warning(
                "resend.notification.rejected",
                extra={
                    "to_domain": _domain(message.to),
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            # Truncated: an error body can echo the payload, and the payload
            # contains the recipient and the message.
            raise EmailError(f"resend returned {response.status_code}: {response.text[:200]}")

        logger.info(
            "resend.notification.ok",
            extra={
                "to_domain": _domain(message.to),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()
