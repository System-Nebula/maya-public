"""Sanitized API validation error responses — never echo request input."""

from __future__ import annotations

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _friendly_message(err: dict) -> str:
    loc = err.get("loc") or ()
    field = loc[-1] if loc else "field"
    err_type = err.get("type", "")
    msg = str(err.get("msg") or "Invalid value")

    if err_type == "string_too_short" and field == "password":
        return "Password must be at least 8 characters"
    if "email" in str(field) or "email" in msg.lower():
        return "Invalid email address"
    if field == "password":
        return "Invalid password"
    if field == "invite_code":
        return "Invite code is required"

    # Strip pydantic "Value error, " prefix from custom validators
    if msg.lower().startswith("value error, "):
        msg = msg[13:]
    return msg


def validation_error_response(exc: RequestValidationError) -> JSONResponse:
    messages = [_friendly_message(e) for e in exc.errors()]
    detail = messages[0] if len(messages) == 1 else messages
    return JSONResponse(status_code=422, content={"detail": detail})
