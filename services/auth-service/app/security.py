"""Authentication primitives shared by protected endpoints.

`get_current_user` (wired in dependencies.py) validates the bearer access
token and yields a CurrentUser. A failure raises AuthenticationError,
which main.py maps to a 401 in the standard error envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class AuthenticationError(RuntimeError):
    """Raised when a request lacks a valid bearer access token."""

    def __init__(
        self,
        code: str = "UNAUTHORIZED",
        message: str = "Authentication required.",
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    role: str


def parse_bearer(authorization: str | None) -> str:
    """Extract the token from an `Authorization: Bearer <token>` header.

    Raises AuthenticationError if the header is missing or malformed.
    """
    if not authorization:
        raise AuthenticationError(message="Missing Authorization header.")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError(message="Authorization header must be 'Bearer <token>'.")
    return parts[1].strip()
