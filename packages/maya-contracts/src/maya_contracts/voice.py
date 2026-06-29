"""Voice assistant contracts — assimilated from voice-agent reference design."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from maya_contracts.common import StrictModel


class VoiceTurnState(str, Enum):
    LOADING = "loading"
    LISTENING = "listening"
    HEARING = "hearing"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    IDLE = "idle"
    ERROR = "error"


class DeliveryMode(str, Enum):
    FULL = "full"
    HYBRID = "hybrid"
    OFF = "off"


class BargeInMode(str, Enum):
    SMART = "smart"
    INSTANT = "instant"
    OFF = "off"


class CloneMode(str, Enum):
    XVEC_ONLY = "xvec_only"
    ICL = "icl"


class EQBandType(str, Enum):
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    PEAKING = "peaking"
    LOWSHELF = "lowshelf"
    HIGHSHELF = "highshelf"
    NOTCH = "notch"


class EQBandSpec(StrictModel):
    band_type: EQBandType
    freq: float
    q: float = 1.0
    gain_db: float = 0.0


class VoiceSession(StrictModel):
    """Per-guild/user session — replaces Hub singleton semantics."""

    session_id: str
    guild_id: str | None = None
    channel_id: str | None = None
    user_id: str | None = None
    active_users: list[str] = Field(default_factory=list)


class VoiceStyleCue(StrictModel):
    """Leading ``VOICE:`` directive parsed from LLM stream."""

    delivery: DeliveryMode | None = None
    instruct: str | None = None
    emotion: str | None = None


class EmotionActionMap(StrictModel):
    """VTube Studio hotkey / expression mapping."""

    mappings: dict[str, str] = Field(default_factory=dict)


class VoiceSettings(StrictModel):
    delivery: DeliveryMode = DeliveryMode.FULL
    barge_mode: BargeInMode = BargeInMode.SMART
    barge_in_enabled: bool = True
    auto_instruct: bool = True
    auto_express: bool = True
    xvec_only: bool = True
    eq_preset: str = "off"
    eq_bands: list[EQBandSpec] = Field(default_factory=list)
    clone_mode: CloneMode = CloneMode.XVEC_ONLY


class VoiceEventType(str, Enum):
    USER = "user"
    AI = "ai"
    STATUS = "status"
    DELIVERY = "delivery"
    EXPRESSION = "expression"
    VTS = "vts"
    BARGE_IN = "barge_in"
    SETTINGS = "settings"
    SPECTRUM = "spectrum"
    READY = "ready"
    ERROR = "error"


class VoiceEvent(StrictModel):
    type: VoiceEventType
    value: str | None = None
    text: str | None = None
    cue: str | None = None
    emotion: str | None = None
    level: float | None = None
    bands: list[float] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
