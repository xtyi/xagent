"""Data-model tests: what actually goes on the wire."""

import unittest

from xagent.messages import Conversation, Message


class TestMessageToWire(unittest.TestCase):
    def test_assistant_reasoning_is_echoed_back(self):
        message = Message(role="assistant", content="answer", reasoning_content="因为...")
        self.assertEqual(
            message.to_wire(),
            {"role": "assistant", "content": "answer", "reasoning_content": "因为..."},
        )

    def test_user_message_never_carries_reasoning(self):
        message = Message(role="user", content="hi", reasoning_content="stray")
        self.assertEqual(message.to_wire(), {"role": "user", "content": "hi"})

    def test_empty_reasoning_is_omitted(self):
        message = Message(role="assistant", content="answer", reasoning_content="")
        self.assertEqual(message.to_wire(), {"role": "assistant", "content": "answer"})

    def test_add_text_and_reasoning_accumulate(self):
        message = Message(role="assistant")
        message.add_text("a")
        message.add_text("b")
        message.add_reasoning("x")
        message.add_reasoning("y")
        self.assertEqual((message.content, message.reasoning_content), ("ab", "xy"))


class TestConversation(unittest.TestCase):
    def test_system_prompt_is_first_and_survives_clear(self):
        conversation = Conversation.with_system_prompt("be nice")
        conversation.add(Message(role="user", content="hi"))
        self.assertEqual(conversation.to_wire()[0], {"role": "system", "content": "be nice"})
        conversation.clear()
        self.assertEqual(len(conversation), 1)
        self.assertEqual(conversation.messages[0].role, "system")

    def test_empty_system_prompt_adds_nothing(self):
        self.assertEqual(len(Conversation.with_system_prompt("")), 0)


if __name__ == "__main__":
    unittest.main()
