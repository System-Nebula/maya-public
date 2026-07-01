"""Email normalization for auth — dev-friendly localhost domains."""

from __future__ import annotations

import os
import re

from pydantic import EmailStr, TypeAdapter, ValidationError

_DEV_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")
_LOCALHOST_SUFFIXES = ("@localhost", ".local")


def _dev_mode() -> bool:
    return os.getenv("ENV", "production").strip().lower() == "development"


def _is_dev_local_email(email: str) -> bool:
    lower = email.lower()
    if lower.endswith("@localhost"):
        return True
    domain = lower.split("@", 1)[-1]
    return domain.endswith(".local")


def normalize_auth_email(value: str) -> str:
    """Normalize and validate an auth email address."""
    email = value.strip().lower()
    if not email:
        raise ValueError("email is required")

    if _dev_mode() and _is_dev_local_email(email):
        if not _DEV_EMAIL.match(email):
            raise ValueError("invalid email address")
        return email

    try:
        return str(TypeAdapter(EmailStr).validate_python(email))
    except ValidationError as exc:
        raise ValueError("invalid email address") from exc
