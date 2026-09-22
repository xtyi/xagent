"""Data-model tests: what actually goes on the wire."""

import pytest

from xagent.messages import Conversation, Message


def test_assistant_reasoning_is_echoed_back():
    message = Message(role="assistant", content="answer", reasoning_content="因为...")
    assert message.to_wire() == {
        "role": "assistant",
        "content": "answer",
        "reasoning_content": "因为...",
    }


@pytest.mark.parametrize("role", ["system", "user", "tool"])
def test_only_assistant_messages_carry_reasoning(role):
    message = Message(role=role, content="hi", reasoning_content="stray")
    assert message.to_wire() == {"role": role, "content": "hi"}


def test_empty_reasoning_is_omitted():
    message = Message(role="assistant", content="answer", reasoning_content="")
    assert message.to_wire() == {"role": "assistant", "content": "answer"}


def test_text_and_reasoning_accumulate_independently():
    message = Message(role="assistant")
    message.add_text("a")
    message.add_text("b")
    message.add_reasoning("x")
    message.add_reasoning("y")
    assert (message.content, message.reasoning_content) == ("ab", "xy")


def test_system_prompt_is_first_and_survives_clear():
    conversation = Conversation.with_system_prompt("be nice")
    conversation.add(Message(role="user", content="hi"))
    assert conversation.to_wire()[0] == {"role": "system", "content": "be nice"}

    conversation.clear()

    assert len(conversation) == 1
    assert conversation.messages[0].role == "system"


def test_empty_system_prompt_adds_nothing():
    assert len(Conversation.with_system_prompt("")) == 0
