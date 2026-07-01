"""Contract validation tests for assistant and voice models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maya_contracts.assistant import (
    AssistantTurn,
    CancelReason,
    LlmProviderProfile,
    SkillKind,
    SkillResult,
)
from maya_contracts.image import (
    AspectRatio,
    BattleState,
    ImagineBattleView,
    ImagineGenerateRequest,
    ImagineVoteRequest,
)
from maya_contracts.voice import (
    BargeInMode,
    DeliveryMode,
    EQBandSpec,
    EQBandType,
    VoiceEvent,
    VoiceEventType,
    VoiceSession,
    VoiceSettings,
    VoiceTurnState,
)


def test_voice_session_per_user():
    session = VoiceSession(session_id="s1", guild_id="g1", user_id="u1")
    assert session.guild_id == "g1"


def test_voice_settings_defaults():
    settings = VoiceSettings()
    assert settings.delivery == DeliveryMode.FULL
    assert settings.barge_mode == BargeInMode.SMART


def test_voice_event_catalog():
    evt = VoiceEvent(type=VoiceEventType.STATUS, value=VoiceTurnState.LISTENING.value)
    assert evt.type == VoiceEventType.STATUS


def test_assistant_turn_and_skill_result():
    turn = AssistantTurn(turn_id="t1", session_id="s1", state=VoiceTurnState.THINKING)
    assert turn.state == VoiceTurnState.THINKING
    skill = SkillResult(skill=SkillKind.IMAGINE, success=True, summary="done")
    assert skill.skill == SkillKind.IMAGINE


def test_llm_provider_profiles():
    assert LlmProviderProfile.LMSTUDIO.value == "lmstudio"


def test_assistant_turn_cancelled_requires_reason():
    with pytest.raises(ValidationError, match="cancel_reason"):
        AssistantTurn(turn_id="t1", session_id="s1", cancelled=True)
    ok = AssistantTurn(
        turn_id="t1", session_id="s1", cancelled=True, cancel_reason=CancelReason.BARGE_IN
    )
    assert ok.cancel_reason == CancelReason.BARGE_IN


def test_assistant_turn_reason_without_cancel_rejected():
    with pytest.raises(ValidationError, match="not cancelled"):
        AssistantTurn(turn_id="t1", session_id="s1", cancel_reason=CancelReason.TIMEOUT)


def test_skill_result_failure_requires_error():
    with pytest.raises(ValidationError, match="requires an error"):
        SkillResult(skill=SkillKind.IMAGINE, success=False)
    with pytest.raises(ValidationError, match="must not carry an error"):
        SkillResult(skill=SkillKind.IMAGINE, success=True, error="boom")
    ok = SkillResult(skill=SkillKind.IMAGINE, success=False, error="provider down")
    assert ok.error == "provider down"


def test_imagine_generate_request_validation():
    with pytest.raises(ValidationError):
        ImagineGenerateRequest(prompt="")
    with pytest.raises(ValidationError):
        ImagineGenerateRequest(prompt="cat", aspect="potato")
    req = ImagineGenerateRequest(prompt="a cat", aspect=AspectRatio.PORTRAIT)
    assert req.aspect == AspectRatio.PORTRAIT


def test_imagine_vote_choice_constrained():
    with pytest.raises(ValidationError):
        ImagineVoteRequest(battle_id="b1", choice="c")
    assert ImagineVoteRequest(battle_id="b1", choice="a").choice == "a"


def test_imagine_battle_view_state_enum():
    view = ImagineBattleView(battle_id="b1", prompt="p", state=BattleState.VOTING)
    assert view.state == BattleState.VOTING
    with pytest.raises(ValidationError):
        ImagineBattleView(battle_id="b1", prompt="p", state="exploded")


def test_eq_band_type_enum():
    band = EQBandSpec(band_type=EQBandType.PEAKING, freq=1000.0)
    assert band.band_type == EQBandType.PEAKING
    with pytest.raises(ValidationError):
        EQBandSpec(band_type="bandpassish", freq=1000.0)
