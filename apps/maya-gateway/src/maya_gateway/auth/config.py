"""Auth configuration helpers."""

from __future__ import annotations

import os


def auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "1").strip().lower() in ("1", "true", "yes")


def auth_enabled() -> bool:
    return not auth_disabled()


def legacy_operator_id() -> str:
    return os.getenv("MAYA_LEGACY_OPERATOR_ID", "local").strip() or "local"
