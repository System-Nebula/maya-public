"""Public imagine / image API contracts."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field

from maya_contracts.common import StrictModel


class ImagineArenaMode(str, Enum):
    DEFAULT = "default"
    STUDIO = "studio"


class AspectRatio(str, Enum):
    SQUARE = "1:1"
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"
    PORTRAIT_4_5 = "4:5"
    LANDSCAPE_3_2 = "3:2"


class BattleState(str, Enum):
    GENERATING = "generating"
    VOTING = "voting"
    RESOLVED = "resolved"
    FAILED = "failed"


class ImagineGenerateRequest(StrictModel):
    prompt: str = Field(min_length=1)
    workflow_id: str = "z-image-turbo-t2i"
    aspect: AspectRatio = AspectRatio.SQUARE
    arena_mode: ImagineArenaMode = ImagineArenaMode.DEFAULT
    magic_prompt: bool = True


class ImagineBattleView(StrictModel):
    battle_id: str
    prompt: str
    state: BattleState
    image_a: str | None = None
    image_b: str | None = None
    error: str | None = None


class ImagineVoteRequest(StrictModel):
    battle_id: str
    choice: Literal["a", "b"]
