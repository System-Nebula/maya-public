"""Structural typing for audio backends.

Consumers (StreamSession, BatchJobRunner, maya-voice TurnLoop) depend on these Protocols,
not concrete classes, so a fake or a GPU backend is interchangeable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class AsrBackendProtocol(Protocol):
    model_id: str

    def transcribe_array(self, audio16: np.ndarray, sample_rate: int = ...) -> str: ...

    def transcribe_file(self, path: str) -> str: ...


@runtime_checkable
class TtsBackendProtocol(Protocol):
    model_id: str

    def stream(self, text: str, *, stop: object | None = ...) -> AsyncIterator[bytes]: ...
