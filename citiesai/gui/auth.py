"""Per-launch session token for local GUI API mutating routes."""

from __future__ import annotations

import secrets

_SESSION_TOKEN: str | None = None
TOKEN_HEADER = "X-CitiesAI-Token"


def init_session_token() -> str:
    global _SESSION_TOKEN
    _SESSION_TOKEN = secrets.token_urlsafe(32)
    return _SESSION_TOKEN


def get_session_token() -> str | None:
    return _SESSION_TOKEN


def validate_session_token(value: str | None) -> bool:
    if not _SESSION_TOKEN:
        return False
    if not value:
        return False
    return secrets.compare_digest(value.strip(), _SESSION_TOKEN)
