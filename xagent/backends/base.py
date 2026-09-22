"""The boundary between our agent and a model provider.

Deliberately narrow: this module knows nothing about HTTP, JSON, or SSE. It
defines only the *shape* of talking to a model.

Design note: there is no "done" event. The iterator running out already means
"this turn is finished", so an explicit done event would carry no extra
information -- one less state to keep in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Literal, Protocol, Sequence

EventKind = Literal["text", "reasoning", "usage"]


class BackendError(RuntimeError):
    """Transport-level failure. Backends raise it; the CLI catches it."""


@dataclass
class StreamEvent:
    """One increment of a model turn.

    `text`      -- user-visible answer text
    `reasoning` -- the model's thinking, which must be echoed back next turn
                   (see probes/000-backend-capabilities.md)
    `usage`     -- token accounting for the completed call
    """

    kind: EventKind
    text: str = ""
    usage: dict[str, Any] | None = None


@dataclass
class ModelParams:
    """Everything a backend needs besides the messages themselves."""

    model: str
    temperature: float = 0.0
    max_tokens: int = 2048


class Backend(Protocol):
    """A source of `StreamEvent`s for one model turn."""

    def stream(
        self, messages: Sequence[dict[str, Any]], params: ModelParams
    ) -> Iterator[StreamEvent]:
        """Yield the events of one assistant turn. Streams lazily."""
        ...
