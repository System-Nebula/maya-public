"""Typed tool contracts — binds a name to input/output models and a callable."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class ToolContract(Generic[InputT, OutputT]):
    """Binds a tool name to its typed input/output models and callable.

    A single data-holder (not a Protocol per capability) so tools can be
    registered/looked up by name — e.g. the graph-lookup tool shared by
    multiple resolvers.
    """

    name: str
    input_model: type[InputT]
    output_model: type[OutputT]
    fn: Callable[[InputT], Awaitable[OutputT]]

    async def invoke(self, payload: InputT) -> OutputT:
        return await self.fn(payload)
