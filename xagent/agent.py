"""The agent loop.

Step 1 version: one turn = send the conversation, stream the answer back into
it. That is *all* an agent does before tools exist -- which is exactly why
Step 2 is interesting: the loop grows a second branch and stops being a
chatbot.

Note what this class does *not* know: HTTP, JSON, SSE, terminals. It receives
events and hands back a finished `Message`.
"""

from __future__ import annotations

from typing import Any, Callable

from .backends.base import Backend, ModelParams, StreamEvent
from .messages import Conversation, Message

EventHandler = Callable[[StreamEvent], None]


def _ignore(event: StreamEvent) -> None:
    return None


class Agent:
    def __init__(
        self,
        backend: Backend,
        params: ModelParams,
        conversation: Conversation,
    ) -> None:
        self._backend = backend
        self._params = params
        self.conversation = conversation
        self.last_usage: dict[str, Any] | None = None

    def checkpoint(self) -> int:
        """History length, so a failed turn can be rolled back exactly."""
        return len(self.conversation)

    def rollback(self, checkpoint: int) -> None:
        """Restore history to `checkpoint`, discarding a half-finished turn."""
        del self.conversation.messages[checkpoint:]

    def send(self, user_text: str, on_event: EventHandler = _ignore) -> Message:
        """Append the user message, run one model turn, return the reply.

        Consuming the whole stream here (rather than yielding events upward) is
        deliberate: the assistant `Message` must be complete before it joins
        the history, and a half-consumed generator would silently break that.
        """
        self.conversation.add(Message(role="user", content=user_text))
        assistant = Message(role="assistant")
        for event in self._backend.stream(self.conversation.to_wire(), self._params):
            if event.kind == "text":
                assistant.add_text(event.text)
            elif event.kind == "reasoning":
                assistant.add_reasoning(event.text)
            elif event.kind == "usage":
                self.last_usage = event.usage
            on_event(event)
        self.conversation.add(assistant)
        return assistant
