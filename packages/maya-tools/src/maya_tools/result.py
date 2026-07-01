"""ToolResult — a lower-level typed envelope than SkillResult.

Carries retryability/attempts/circuit_state, which SkillResult (a
user/skill-facing envelope) has no field for. Bridges into SkillResult at
the cog/skill boundary via ``to_skill_result`` rather than merging the two
models — keeps ``maya-contracts`` free of a ``maya-tools`` dependency.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    tool_name: str
    success: bool
    value: T | None = None
    error: str | None = None
    retryable: bool = False
    attempts: int = 1
    latency_ms: float | None = None
    circuit_state: str | None = None  # "closed" | "open" | "half_open"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "ToolResult":
        if not self.success and not self.error:
            raise ValueError("failed ToolResult requires an error message")
        if self.success and self.value is None:
            raise ValueError("successful ToolResult requires a value")
        return self

    def to_skill_result(self, skill, *, summary: str | None = None):
        from maya_contracts.assistant import SkillResult

        return SkillResult(
            skill=skill,
            success=self.success,
            summary=summary,
            error=self.error,
            metadata={**self.metadata, "tool_name": self.tool_name, "attempts": self.attempts},
        )
