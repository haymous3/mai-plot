"""/notifications/preferences + /notifications/unsubscribe routes (SCRUM-122).

A signed-in user reads/updates their per-channel preferences; the dispatch core
honours them (in-app is always delivered). The unsubscribe endpoint is
unauthenticated — clicked from an email — and guarded by the HMAC token the email
carried, so it can only opt out the user it was issued for.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.dependencies import SettingsDep, get_current_user, get_preference_repo
from app.repositories.preference_repo import PreferenceRepository
from app.schemas.preferences import PreferenceResponse, PreferenceUpdate
from app.security import CurrentUser
from app.services.unsubscribe_token import verify_unsubscribe_token

router = APIRouter(prefix="/notifications", tags=["preferences"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PreferenceRepoDep = Annotated[PreferenceRepository, Depends(get_preference_repo)]

_UNSUBSCRIBED_HTML = (
    '<!doctype html><html><body style="font-family:Arial,sans-serif;">'
    "<h2>You're unsubscribed</h2>"
    "<p>You will no longer receive Maiplot notification emails. You can re-enable "
    "them anytime from your notification settings.</p></body></html>"
)


def _response(prefs: object) -> PreferenceResponse:
    return PreferenceResponse(
        push_enabled=prefs.push_enabled,  # type: ignore[attr-defined]
        sms_enabled=prefs.sms_enabled,  # type: ignore[attr-defined]
        email_enabled=prefs.email_enabled,  # type: ignore[attr-defined]
    )


@router.get("/preferences", response_model=PreferenceResponse)
async def get_preferences(caller: CurrentUserDep, repo: PreferenceRepoDep) -> PreferenceResponse:
    """The caller's channel preferences (defaults if never set)."""
    return _response(await repo.get(caller.user_id))


@router.patch("/preferences", response_model=PreferenceResponse)
async def update_preferences(
    payload: PreferenceUpdate, caller: CurrentUserDep, repo: PreferenceRepoDep
) -> PreferenceResponse:
    """Partially update the caller's preferences; returns the new state."""
    prefs = await repo.update(
        caller.user_id,
        push_enabled=payload.push_enabled,
        sms_enabled=payload.sms_enabled,
        email_enabled=payload.email_enabled,
    )
    return _response(prefs)


@router.get("/unsubscribe", response_model=None)
async def unsubscribe(
    settings: SettingsDep,
    repo: PreferenceRepoDep,
    uid: Annotated[UUID, Query()],
    token: Annotated[str, Query()],
) -> HTMLResponse | JSONResponse:
    """Disable email for the user named in a valid signed link. No auth — the
    HMAC token is the proof. A bad/missing token changes nothing (400)."""
    if not verify_unsubscribe_token(uid, token, secret=settings.unsubscribe_secret):
        return JSONResponse(
            status_code=400,
            content={
                "error_code": "INVALID_UNSUBSCRIBE_TOKEN",
                "message": "The unsubscribe link is invalid.",
                "details": {},
            },
        )
    await repo.update(uid, email_enabled=False)
    return HTMLResponse(content=_UNSUBSCRIBED_HTML)
