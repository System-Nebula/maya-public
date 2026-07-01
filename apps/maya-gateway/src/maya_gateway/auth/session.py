"""Signed session cookie helpers."""

from __future__ import annotations

import os
import time
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "maya_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret:
        secret = os.getenv("SESSION_SECRET_FALLBACK", "dev-insecure-change-me")
    return URLSafeTimedSerializer(secret, salt="maya-gateway-session")


def sign_session(user_id: str) -> str:
    payload = {"user_id": user_id, "iat": int(time.time())}
    return _serializer().dumps(payload)


def verify_session(token: str) -> dict[str, Any] | None:
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
