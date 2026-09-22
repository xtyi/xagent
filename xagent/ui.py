"""Terminal rendering.

Strictly a display layer: it decides *how* things look, never *what* happens.
Streaming reasoning and streaming answer text need different treatment because
they are two independent streams of tokens (see probes/000).
"""

from __future__ import annotations

import sys
from typing import IO, Any, Sequence

from .backends.base import StreamEvent

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"


class Renderer:
    def __init__(
        self,
        *,
        show_reasoning: bool = False,
        show_usage: bool = True,
        out: IO[str] | None = None,
        err: IO[str] | None = None,
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.show_reasoning = show_reasoning
        self.show_usage = show_usage
        self.usage: dict[str, Any] | None = None
        self._reasoning_open = False
        self._reasoning_started = False

    def begin_turn(self) -> None:
        self.usage = None
        self._reasoning_open = False
        self._reasoning_started = False
        self.out.write(f"{BOLD}xagent>{RESET} ")
        self.out.flush()

    def on_event(self, event: StreamEvent) -> None:
        if event.kind == "reasoning":
            if not self.show_reasoning:
                return
            if not self._reasoning_started:
                # Enter dim mode once; `_close_reasoning` leaves it again.
                self.out.write(f"\n{DIM}[thinking] ")
                self._reasoning_started = True
            self._reasoning_open = True
            self.out.write(event.text)
        elif event.kind == "text":
            self._close_reasoning()
            self.out.write(event.text)
        elif event.kind == "usage":
            self.usage = event.usage
        self.out.flush()

    def end_turn(self) -> None:
        self._close_reasoning()
        self.out.write("\n")
        if self.show_usage and self.usage:
            prompt = self.usage.get("prompt_tokens", "?")
            completion = self.usage.get("completion_tokens", "?")
            self.out.write(f"{DIM}[tokens: {prompt} in / {completion} out]{RESET}\n")
        self.out.flush()

    def note(self, text: str) -> None:
        self.out.write(text if text.endswith("\n") else text + "\n")
        self.out.flush()

    def status(self, fields: Sequence[tuple[str, str]]) -> None:
        """One dim line summarising the session: model, thinking, ...

        Takes pairs rather than a fixed shape so later per-session settings
        (permissions, workspace, ...) can join the line without changing this.
        """
        rendered = " ".join(f"{key}={value}" for key, value in fields)
        self.out.write(f"{DIM}[{rendered}]{RESET}\n")
        self.out.flush()

    def diagnostic(self, text: str) -> None:
        """Out-of-band line -- e.g. where credentials came from. Goes to stderr."""
        self.err.write(text if text.endswith("\n") else text + "\n")
        self.err.flush()

    def error(self, text: str) -> None:
        self.out.write(f"{BOLD}error:{RESET} {text}")
        if not text.endswith("\n"):
            self.out.write("\n")
        self.out.flush()

    def _close_reasoning(self) -> None:
        if self._reasoning_open:
            self.out.write(f"{RESET}\n")
            self._reasoning_open = False
