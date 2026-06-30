"""Shared ONNX base for Parakeet TDT/CTC backends — STUB (pass 1).

Parakeet TDT and CTC share session setup and feature extraction; that lives here so the
two real backends (follow-on) don't copy-paste. ``onnxruntime`` is imported lazily.
"""

from __future__ import annotations

import numpy as np

from maya_audio.backends.base import AsrBackend


class OnnxParakeetBackend(AsrBackend):
    supports_streaming = False

    def __init__(self, model_path: str, model_id: str = "parakeet") -> None:
        self.model_path = model_path
        self.model_id = model_id
        # Follow-on: import onnxruntime; self._session = onnxruntime.InferenceSession(model_path)
        raise NotImplementedError("OnnxParakeetBackend is a pass-1 stub (follow-on).")

    def _infer(self, audio16: np.ndarray) -> str:  # pragma: no cover - stub
        raise NotImplementedError
