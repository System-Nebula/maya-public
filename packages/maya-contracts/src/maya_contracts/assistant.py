"""Assistant core contracts — Siri/Alexa-style turn loop and skill envelope."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from maya_contracts.common import StrictModel
from maya_contracts.voice import VoiceTurnState


class SkillKind(str, Enum):
    VOICE = "voice"
    IMAGINE = "imagine"
    RESEARCH = "research"
    INBOX = "inbox"
    MUSIC = "music"
    FEED = "feed"


class CancelReason(str, Enum):
    BARGE_IN = "barge_in"
    USER_STOP = "user_stop"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


class AssistantTurn(StrictModel):
    turn_id: str
    session_id: str
    state: VoiceTurnState = VoiceTurnState.IDLE
    user_text: str | None = None
    assistant_text: str | None = None
    skill: SkillKind | None = None
    cancelled: bool = False
    cancel_reason: CancelReason | None = None

    @model_validator(mode="after")
    def _check_cancel(self) -> AssistantTurn:
        if self.cancelled and self.cancel_reason is None:
            raise ValueError("cancelled turn requires a cancel_reason")
        if not self.cancelled and self.cancel_reason is not None:
            raise ValueError("cancel_reason set on a turn that is not cancelled")
        return self


class SkillResult(StrictModel):
    """Generic envelope for imagine / research / inbox skill responses."""

    skill: SkillKind
    success: bool
    summary: str | None = None
    artifact_url: str | None = None
    run_id: UUID | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_error(self) -> SkillResult:
        if not self.success and not self.error:
            raise ValueError("failed SkillResult requires an error message")
        if self.success and self.error:
            raise ValueError("successful SkillResult must not carry an error")
        return self


class LlmProviderProfile(str, Enum):
    LMSTUDIO = "lmstudio"
    VLLM = "vllm"
    OPENAI = "openai"
    FAKE = "fake"
