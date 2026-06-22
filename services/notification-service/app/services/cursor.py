"""Opaque keyset-pagination cursor for the notification feed (SCRUM-82).

The feed orders by (created_at DESC, id DESC); a cursor encodes the last row a
client saw so the next page resumes strictly after it. We encode the pair as a
base64-urlsafe blob so the value is opaque to clients — they must round-trip
exactly what we hand back, never construct one. Keyset (not OFFSET) keeps the
query O(page) regardless of how deep the user scrolls.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

_SEP = "|"


class CursorInvalid(ValueError):
    """Raised when a client supplies a cursor we can't decode."""


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: UUID


def encode_cursor(created_at: datetime, id: UUID) -> str:
    raw = f"{created_at.isoformat()}{_SEP}{id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(raw: str) -> Cursor:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        created_str, id_str = decoded.split(_SEP, 1)
        return Cursor(created_at=datetime.fromisoformat(created_str), id=UUID(id_str))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise CursorInvalid("Malformed pagination cursor.") from exc
