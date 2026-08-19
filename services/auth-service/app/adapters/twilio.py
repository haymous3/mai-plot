"""Twilio adapter — SMS dispatch for OTP messages (SCRUM-175).

Replaces the Termii adapter this service used to carry. Three pieces, the
same shape every other adapter here follows:
  * SmsClient — Protocol every callable site depends on.
  * HttpTwilioClient — real adapter, calls Twilio's Messages REST API.
  * InMemoryTwilioClient — in-process fake. Captures (phone, message)
    pairs so tests can assert what was sent without hitting the network.

Production binds the real one via TWILIO_USE_FAKE=false. CI and local dev
get the fake by default, matching .env.example.

Why Programmable SMS and not Twilio Verify: CLAUDE.md §4 pins the OTP
semantics (6-digit, 5-minute expiry, single-use) as server-side
non-negotiables. Verify would move that state to a third party, so this
adapter stays a dumb transport and app/services/otp.py keeps ownership of
code generation, hashing and expiry.

DELIVERABILITY WARNING (SCRUM-175): every recipient in this system is a
Nigerian mobile (+234[789]XXXXXXXXX — see app/validators/phone.py), and the
configured sender is a US long code. Nigerian carriers filter A2P traffic
under NCC rules and generally require a registered alphanumeric sender ID;
US long-code A2P to NG is frequently dropped by the carrier *after* Twilio
reports success. A 201 from this adapter therefore means "Twilio accepted
it", never "the user received it". Delivery must be confirmed out of band
until a Nigerian sender ID is registered.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class SmsClient(Protocol):
    async def send_sms(self, phone: str, message: str) -> None:  # pragma: no cover - protocol
        ...


@dataclass
class SentMessage:
    phone: str
    message: str


class SmsError(RuntimeError):
    """Raised when the SMS provider rejects or fails to deliver a dispatch."""


@dataclass
class InMemoryTwilioClient:
    """Test double — captures sent messages in-process.

    Construct fresh per test (the registration service accepts the client
    by injection) so there is no global state to clear between tests.
    """

    sent: list[SentMessage] = field(default_factory=list)
    fail_next: bool = False

    async def send_sms(self, phone: str, message: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise SmsError("simulated Twilio failure")
        self.sent.append(SentMessage(phone=phone, message=message))


class HttpTwilioClient:
    """Calls Twilio's Messages endpoint. One client per service process; httpx
    handles connection pooling under the hood.

    Twilio's REST API is form-encoded (not JSON) and authenticates with HTTP
    Basic — Account SID as the username, Auth Token as the password. We call
    it directly rather than pulling in the `twilio` SDK: the SDK is sync-only
    at this call site and every other adapter in this service is raw httpx.
    """

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        base_url: str,
        timeout_seconds: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._from_number = from_number
        # `transport` is a test seam: tests pass httpx.MockTransport so the
        # auth + encoding wiring below is exercised for real rather than being
        # swapped out along with the client.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            auth=(account_sid, auth_token),
            transport=transport,
        )

    async def send_sms(self, phone: str, message: str) -> None:
        # Twilio requires full E.164 for both ends, leading + included — the
        # opposite of Termii, which wanted the + stripped. Our phone validator
        # already hands us canonical +234... so this passes through as-is.
        payload = {
            "To": phone,
            "From": self._from_number,
            "Body": message,
        }
        path = f"/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        started = time.perf_counter()
        try:
            response = await self._client.post(path, data=payload)
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "twilio.dispatch.failed",
                extra={"phone_suffix": phone[-4:], "duration_ms": duration_ms, "error": str(exc)},
            )
            raise SmsError(str(exc)) from exc

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "twilio.dispatch.ok",
            extra={
                "phone_suffix": phone[-4:],
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        # Never log the response body: it echoes the message Body back, which
        # contains the plaintext OTP.
        if response.status_code >= 400:
            raise SmsError(f"twilio returned {response.status_code}")

    async def aclose(self) -> None:
        await self._client.aclose()


def build_sms_client(
    *,
    use_fake: bool,
    account_sid: str,
    auth_token: str,
    from_number: str,
    base_url: str,
    timeout_seconds: float,
) -> SmsClient:
    """Factory — pick the fake or real client based on settings."""
    if use_fake:
        return InMemoryTwilioClient()
    return HttpTwilioClient(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
