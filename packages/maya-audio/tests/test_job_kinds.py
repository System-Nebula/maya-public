"""Every AudioJobKind has a non-empty stage plan."""

from __future__ import annotations

import pytest

from maya_audio.jobs.kinds import stages_for
from maya_contracts.audio_jobs import AudioJobKind


@pytest.mark.parametrize("kind", list(AudioJobKind))
def test_every_kind_has_stages(kind: AudioJobKind) -> None:
    stages = stages_for(kind)
    assert stages
    assert all(isinstance(s, str) and s for s in stages)
