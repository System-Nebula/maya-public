"""Voice control-panel + conversational-pipeline contracts.

These back the drop-in voice SDK (Alpine components) and the gateway pipeline
that turns an operator utterance into Maya's reply. Kept separate from
``maya_contracts.voice`` (runtime SSE / session contracts) so panel models can
use lenient JSON parsing while runtime models stay on ``StrictModel``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _VoicePanelModel(BaseModel):
    """Lenient base — browser SDK sends enum values as strings."""

    model_config = ConfigDict(extra="ignore")


class DetectionMode(str, Enum):
    VAD = "vad"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class TurnRole(str, Enum):
    OPERATOR = "operator"
    MAYA = "maya"


class TurnIntent(str, Enum):
    GREETING = "greeting"
    QUESTION = "question"
    COMMAND = "command"
    FAREWELL = "farewell"
    STATEMENT = "statement"
    EMPTY = "empty"


class OperatorVoiceSettings(_VoicePanelModel):
    input_device_id: str | None = None
    output_device_id: str | None = None
    input_gain: float = 1.0
    noise_suppression: bool = True
    detection_mode: DetectionMode = DetectionMode.VAD
    vad_threshold: float = 0.02
    vad_hangover_ms: int = 600
    push_to_talk_key: str = "Space"
    wispr_model: str = "wispr-flow-1"
    language: str = "en"
    auto_punctuation: bool = True
    filler_removal: bool = True
    reasoning_model: str = "maya-reason-mini"
    persona: str = "maya"


class ConversationTurn(_VoicePanelModel):
    role: TurnRole
    text: str


class VoiceTurnRequest(_VoicePanelModel):
    transcript: str
    settings: OperatorVoiceSettings | None = None
    history: list[ConversationTurn] = Field(default_factory=list)


class VoiceTurnResponse(_VoicePanelModel):
    transcript_raw: str
    transcript_clean: str
    intent: TurnIntent
    maya_turn: str
    reasoning_model: str
    reasoning_trace: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class VoiceDefaultsResponse(_VoicePanelModel):
    default_settings: OperatorVoiceSettings
    detection_modes: list[str]
    wispr_models: list[str]
    reasoning_models: list[str]
    languages: list[str]
