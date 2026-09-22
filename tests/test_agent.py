"""Loop tests: does one turn produce the right history, and is it transactional?

Everything here runs against MockBackend, so the suite needs no network.
"""

import pytest

from xagent.agent import Agent
from xagent.backends.base import ModelParams, StreamEvent
from xagent.backends.mock import MockBackend
from xagent.messages import Conversation

PARAMS = ModelParams(model="mock")


def text(value: str) -> StreamEvent:
    return StreamEvent(kind="text", text=value)


def test_one_turn_appends_user_then_assistant():
    backend = MockBackend(
        responses=[
            [
                StreamEvent(kind="reasoning", text="because"),
                text("hello"),
                text(" world"),
            ]
        ]
    )
    agent = Agent(backend, PARAMS, Conversation.with_system_prompt("sys"))

    reply = agent.send("hi")

    assert reply.content == "hello world"
    assert reply.reasoning_content == "because"
    assert [(message.role, message.content) for message in agent.conversation] == [
        ("system", "sys"),
        ("user", "hi"),
        ("assistant", "hello world"),
    ]


def test_usage_event_is_recorded():
    backend = MockBackend(
        responses=[[StreamEvent(kind="usage", usage={"prompt_tokens": 3})]]
    )
    agent = Agent(backend, PARAMS, Conversation())

    agent.send("hi")

    assert agent.last_usage == {"prompt_tokens": 3}


def test_events_are_forwarded_to_the_renderer_hook():
    backend = MockBackend(responses=[[text("a"), text("b")]])
    agent = Agent(backend, PARAMS, Conversation())
    seen = []

    agent.send("hi", seen.append)

    assert [event.text for event in seen] == ["a", "b"]


def test_second_turn_replays_previous_reasoning_to_the_backend():
    """The DeepSeek thinking-mode constraint, verified at the loop level."""
    backend = MockBackend(
        responses=[
            [StreamEvent(kind="reasoning", text="I will say hi."), text("hi")],
            [text("again")],
        ]
    )
    agent = Agent(backend, PARAMS, Conversation())

    agent.send("hello")
    agent.send("say it again")

    assistant_messages = [
        message for message in backend.requests[1] if message["role"] == "assistant"
    ]
    assert assistant_messages[0]["reasoning_content"] == "I will say hi."


def test_echo_backend_answers_with_the_last_user_message():
    agent = Agent(MockBackend.echo(), PARAMS, Conversation())
    assert agent.send("ping").content == "echo: ping"


def test_rollback_discards_a_failed_turn():
    class ExplodingBackend:
        def stream(self, messages, params):
            yield text("partial")
            raise RuntimeError("connection dropped")

    agent = Agent(ExplodingBackend(), PARAMS, Conversation.with_system_prompt("sys"))
    checkpoint = agent.checkpoint()

    with pytest.raises(RuntimeError, match="connection dropped"):
        agent.send("hi")

    agent.rollback(checkpoint)
    assert [message.role for message in agent.conversation] == ["system"]
