"""OAuth state signing for Google and Discord flows."""

from __future__ import annotations

import os
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

OAUTH_STATE_MAX_AGE = 600  # 10 minutes


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("SESSION_SECRET", "").strip() or os.getenv(
        "SESSION_SECRET_FALLBACK", "dev-insecure-change-me"
    )
    return URLSafeTimedSerializer(secret, salt="maya-gateway-oauth-state")


def sign_oauth_state(payload: dict[str, Any]) -> str:
    return _serializer().dumps(payload)


def verify_oauth_state(token: str) -> dict[str, Any] | None:
    try:
        data = _serializer().loads(token, max_age=OAUTH_STATE_MAX_AGE)
        return data if isinstance(data, dict) else None
    except (BadSignature, SignatureExpired):
        return None
