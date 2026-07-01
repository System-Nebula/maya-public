"""Maya voice stack — vendored from jov4n/voice-agent with benchmark and OTEL tracing."""

from typing import TYPE_CHECKING

from maya_voice_stack.metrics import ConversationTrace, StageTimings
from maya_voice_stack.tracing import init_tracing

if TYPE_CHECKING:
    from maya_voice_stack.benchmark import TurnResult

__all__ = [
    "ConversationTrace",
    "StageTimings",
    "TurnResult",
    "init_tracing",
    "run_turn_from_wav",
]


def run_turn_from_wav(*args, **kwargs):  # noqa: ANN002, ANN003
    from maya_voice_stack.benchmark import run_turn_from_wav as _run

    return _run(*args, **kwargs)
