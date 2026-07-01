"""Shared staged-pipeline logging convention.

Enforces the same diagnostic pattern used in cogs/chat.py's mention handler
(and maya_tools.runner's tool-call staging) everywhere a multi-hop pipeline
needs "which stage did this reach before it went silent" visibility. Every
call logs a structlog line and, if given an active span, an OTEL span event
— so the trace is inspectable with or without a collector configured.
"""

from __future__ import annotations

from typing import Callable

import structlog


def make_stage_logger(component: str) -> Callable[..., None]:
    """Return a ``stage(name, span=None, **fields)`` callable bound to ``component``.

    Every caller in the bot (mention handling, /play, future pipelines)
    should use this instead of hand-rolling its own logging convention, so
    "which stage did it reach" is answerable the same way everywhere.
    """
    logger = structlog.get_logger()

    def _stage(name: str, span=None, **fields) -> None:
        logger.info(f"{component}.stage", stage=name, **fields)
        if span is not None:
            span.add_event(name, attributes={k: str(v) for k, v in fields.items()})

    return _stage
