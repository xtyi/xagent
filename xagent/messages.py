"""The conversation data model -- and the boundary to the wire format.

This is the only place that decides how a message is expressed as a dict for
the OpenAI-compatible API. Everything else in the program passes `Message`
objects around. Keeping that conversion in one place is what lets Step 2 add
tool calls without touching the agent loop's understanding of history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str = ""
    # DeepSeek's thinking models require the previous assistant turn's
    # reasoning to be sent back verbatim; dropping it fails with HTTP 400.
    # See probes/000-backend-capabilities.md.
    reasoning_content: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """Expressed as the provider expects to receive it."""
        wire: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant" and self.reasoning_content:
            wire["reasoning_content"] = self.reasoning_content
        return wire

    def add_text(self, text: str) -> None:
        self.content += text

    def add_reasoning(self, text: str) -> None:
        self.reasoning_content = (self.reasoning_content or "") + text


@dataclass
class Conversation:
    """An ordered message list plus its wire view.

    Kept as the single owner of history so later steps (context trimming,
    persistence, resume) have exactly one place to hook into.
    """

    messages: list[Message] = field(default_factory=list)

    @classmethod
    def with_system_prompt(cls, prompt: str) -> Conversation:
        conversation = cls()
        if prompt:
            conversation.add(Message(role="system", content=prompt))
        return conversation

    def add(self, message: Message) -> Message:
        self.messages.append(message)
        return message

    def to_wire(self) -> list[dict[str, Any]]:
        return [message.to_wire() for message in self.messages]

    def clear(self) -> None:
        """Drop history but keep the system prompt (the first message)."""
        self.messages = self.messages[:1]

    def __len__(self) -> int:
        return len(self.messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self.messages)
