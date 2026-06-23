"""Web Push adapter — in-browser push via the Web Push Protocol + VAPID (SCRUM-79).

Phase 1 uses Web Push (not FCM). Three pieces, mirroring the Termii adapter:
  * WebPushClient — Protocol every callable site depends on.
  * PyWebPushClient — real adapter over `pywebpush` (VAPID-signed, payload
    encrypted to the subscription's keys). pywebpush is synchronous, so the
    blocking call runs in a thread.
  * InMemoryWebPushClient — in-process fake; captures (endpoint, payload) so
    tests assert what was pushed without crypto or a push service.

Two failure modes are distinguished because they need opposite handling:
  * WebPushSubscriptionExpired — the push service returned 404/410, the
    subscription is dead. Terminal: the caller deletes it; never retried.
  * WebPushError — any other transport failure. Transient: the Celery task
    retries with backoff.

Production binds the real client via WEB_PUSH_USE_FAKE=false + a VAPID keypair;
CI/local get the fake by default.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PushSubscriptionInfo:
    """The browser PushSubscription fields needed to encrypt + deliver a push."""

    endpoint: str
    p256dh: str
    auth: str


class WebPushError(RuntimeError):
    """A transient Web Push delivery failure — safe to retry."""


class WebPushSubscriptionExpired(Exception):
    """The push service reports the subscription is gone (404/410). Terminal —
    the subscription should be deleted, not retried. Deliberately NOT a subclass
    of WebPushError so retry logic never catches it."""


class WebPushClient(Protocol):
    async def send(
        self, subscription: PushSubscriptionInfo, payload: str
    ) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class SentPush:
    endpoint: str
    payload: str


@dataclass
class InMemoryWebPushClient:
    """Test double — captures pushes in-process. `fail_next` simulates a
    transient error, `gone_next` an expired subscription."""

    sent: list[SentPush] = field(default_factory=list)
    fail_next: bool = False
    gone_next: bool = False

    async def send(self, subscription: PushSubscriptionInfo, payload: str) -> None:
        if self.gone_next:
            self.gone_next = False
            raise WebPushSubscriptionExpired("simulated expired subscription")
        if self.fail_next:
            self.fail_next = False
            raise WebPushError("simulated Web Push failure")
        self.sent.append(SentPush(endpoint=subscription.endpoint, payload=payload))


class PyWebPushClient:
    """Real adapter — VAPID-signed Web Push via the `pywebpush` library."""

    _GONE_STATUSES = (404, 410)

    def __init__(self, *, vapid_private_key: str, vapid_subject: str, ttl: int) -> None:
        self._vapid_private_key = vapid_private_key
        self._vapid_subject = vapid_subject
        self._ttl = ttl

    async def send(self, subscription: PushSubscriptionInfo, payload: str) -> None:
        import asyncio

        await asyncio.to_thread(self._send_sync, subscription, payload)

    def _send_sync(self, subscription: PushSubscriptionInfo, payload: str) -> None:
        from pywebpush import WebPushException, webpush

        started = time.perf_counter()
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=self._vapid_private_key,
                vapid_claims={"sub": self._vapid_subject},
                ttl=self._ttl,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            duration_ms = (time.perf_counter() - started) * 1000
            if status in self._GONE_STATUSES:
                logger.info(
                    "web_push.subscription_expired",
                    extra={"status_code": status, "duration_ms": duration_ms},
                )
                raise WebPushSubscriptionExpired(str(status)) from exc
            logger.error(
                "web_push.dispatch.failed",
                extra={"status_code": status, "duration_ms": duration_ms, "error": str(exc)},
            )
            raise WebPushError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info("web_push.dispatch.ok", extra={"duration_ms": duration_ms})


def build_web_push_client(
    *,
    use_fake: bool,
    vapid_private_key: str,
    vapid_subject: str,
    ttl: int,
) -> WebPushClient:
    """Factory — pick the fake or real client based on settings."""
    if use_fake:
        return InMemoryWebPushClient()
    return PyWebPushClient(
        vapid_private_key=vapid_private_key,
        vapid_subject=vapid_subject,
        ttl=ttl,
    )
