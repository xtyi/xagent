"""Offline backend: deterministic, no network, no credentials.

Two uses: `tests/` runs the real agent loop against it, and `--mock` lets the
whole program be exercised before any API key exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

from .base import ModelParams, StreamEvent

Responder = Callable[[Sequence[dict[str, Any]]], Sequence[StreamEvent]]


@dataclass
class MockBackend:
    """Replays canned events, either from a script or from a callback.

    `requests` records every message list it was handed -- this is how tests
    assert on what the agent *actually sent*, not just on what it printed.
    """

    responses: Sequence[Sequence[StreamEvent]] | None = None
    responder: Responder | None = None
    loop: bool = False
    requests: list[list[dict[str, Any]]] = field(default_factory=list)
    _cursor: int = 0

    def stream(
        self, messages: Sequence[dict[str, Any]], params: ModelParams
    ) -> Iterator[StreamEvent]:
        self.requests.append([dict(message) for message in messages])
        if self.responder is not None:
            yield from self.responder(messages)
            return
        script = self.responses or []
        if self._cursor >= len(script):
            if not self.loop:
                raise RuntimeError("MockBackend script exhausted")
            self._cursor = 0
        yield from script[self._cursor]
        self._cursor += 1

    @classmethod
    def echo(cls) -> MockBackend:
        """Repeat the last user message back, with a little reasoning."""

        def respond(messages: Sequence[dict[str, Any]]) -> Sequence[StreamEvent]:
            last_user = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                "",
            )
            return [
                StreamEvent(kind="reasoning", text="The user wants an echo. I repeat it."),
                StreamEvent(kind="text", text=f"echo: {last_user}"),
                StreamEvent(kind="usage", usage={"prompt_tokens": 0, "completion_tokens": 0}),
            ]

        return cls(responder=respond)
