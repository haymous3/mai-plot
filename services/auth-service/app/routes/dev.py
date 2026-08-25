"""Local-development helpers. NEVER reachable outside ENV=local.

Why this exists: with the fake SMS adapter bound (TWILIO_USE_FAKE=true, the
default for local and CI), the OTP is generated and bcrypt-hashed into
otp_codes but the plaintext only ever reaches an in-process list. Nothing can
read it — app/adapters/twilio.py deliberately never logs the code, and that
property is not up for negotiation (CLAUDE.md §4). The result was that a
developer could call /auth/register locally but could never complete
/auth/otp/verify.

This endpoint closes that gap for local dev only. It reads the code back out
of InMemoryTwilioClient — the same object the tests inspect — and returns it.

FOUR independent things must ALL hold before a code can be read. Any one of
them failing is sufficient to make this endpoint useless to an attacker:

  1. PATH — mounted at /dev/*, which Kong does not route (infra/kong/kong.yml
     lists every public path; /dev is not among them). auth-service is a
     PRIVATE service on Render, reachable only through Kong, so even if this
     router existed in staging it could not be reached from outside.

  2. REGISTRATION — app/main.py only includes this router when settings.env
     == "local" AND settings.twilio_use_fake. In staging and production the
     routes are never registered, so they 404 like any unknown path. This is
     the primary gate: the endpoint does not exist rather than being guarded.

  3. RUNTIME RE-CHECK — every handler re-asserts the same conditions, so a
     future refactor that registers this router unconditionally still cannot
     leak. It answers 404 (not 403) so it does not confirm its own existence.

  4. CLIENT TYPE — only InMemoryTwilioClient is ever read. If a real Twilio
     client is bound there is nothing to read and the request is refused, so
     this can never surface a code that was genuinely sent to a handset.

If you are reading this because you want the same convenience in staging:
don't. Use the email magic-link path, which is designed to be user-facing.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.adapters.twilio import InMemoryTwilioClient, SmsClient
from app.config import Settings, get_settings
from app.dependencies import get_sms_client
from app.validators.phone import InvalidPhoneError, normalise_nigerian_phone

router = APIRouter(prefix="/dev", tags=["dev"])

_CODE_RE = re.compile(r"\b(\d{6})\b")

SettingsDep = Annotated[Settings, Depends(get_settings)]
SmsClientDep = Annotated[SmsClient, Depends(get_sms_client)]


def dev_routes_enabled(settings: Settings) -> bool:
    """The single source of truth for whether these routes may exist.

    Used both by main.py (to decide registration) and by each handler (to
    re-check at call time). Keeping it in one function means the two can
    never drift apart.
    """
    return settings.env == "local" and settings.twilio_use_fake


def _not_found() -> JSONResponse:
    """Deliberately indistinguishable from an unregistered path."""
    return JSONResponse(
        status_code=404,
        content={"error_code": "NOT_FOUND", "message": "Not Found", "details": {}},
    )


@router.get("/otp/latest")
async def latest_otp(
    settings: SettingsDep,
    sms: SmsClientDep,
    phone: str | None = None,
) -> JSONResponse:
    """Return the most recent OTP the fake adapter "sent".

    `phone` is optional and accepts either local (08012345678) or E.164
    (+2348012345678) form; without it, the latest message to any number is
    returned. Ordering is the fake's insertion order, i.e. chronological.
    """
    if not dev_routes_enabled(settings):
        return _not_found()
    if not isinstance(sms, InMemoryTwilioClient):
        # A real client is bound — there is no in-process copy of the code, and
        # this endpoint must never become a way to read live traffic.
        return _not_found()

    messages = list(sms.sent)
    if phone is not None:
        try:
            wanted = normalise_nigerian_phone(phone)
        except InvalidPhoneError as exc:
            return JSONResponse(
                status_code=422,
                content={
                    "error_code": "VALIDATION_ERROR",
                    "message": str(exc),
                    "details": {},
                },
            )
        messages = [m for m in messages if m.phone == wanted]

    if not messages:
        return JSONResponse(
            status_code=404,
            content={
                "error_code": "NO_OTP_SENT",
                "message": "The fake adapter has not sent a code for that number.",
                "details": {},
            },
        )

    last = messages[-1]
    match = _CODE_RE.search(last.message)
    return JSONResponse(
        status_code=200,
        content={
            "phone": last.phone,
            "code": match.group(1) if match else None,
            "message": last.message,
            "total_sent": len(sms.sent),
        },
    )
