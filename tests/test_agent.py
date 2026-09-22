"""Loop tests: does one turn produce the right history, and is it transactional?

Everything here runs against MockBackend, so the suite needs no network.
"""

import unittest

from xagent.agent import Agent
from xagent.backends.base import ModelParams, StreamEvent
from xagent.backends.mock import MockBackend
from xagent.messages import Conversation

PARAMS = ModelParams(model="mock")


def scripted(*turns):
    return MockBackend(responses=turns)


class TestAgentTurn(unittest.TestCase):
    def test_one_turn_appends_user_then_assistant(self):
        backend = scripted(
            [
                StreamEvent(kind="reasoning", text="because"),
                StreamEvent(kind="text", text="hello"),
                StreamEvent(kind="text", text=" world"),
            ]
        )
        agent = Agent(backend, PARAMS, Conversation.with_system_prompt("sys"))

        reply = agent.send("hi")

        self.assertEqual(reply.content, "hello world")
        self.assertEqual(reply.reasoning_content, "because")
        self.assertEqual(
            [(m.role, m.content) for m in agent.conversation],
            [("system", "sys"), ("user", "hi"), ("assistant", "hello world")],
        )

    def test_usage_event_is_recorded(self):
        backend = scripted([StreamEvent(kind="usage", usage={"prompt_tokens": 3})])
        agent = Agent(backend, PARAMS, Conversation())
        agent.send("hi")
        self.assertEqual(agent.last_usage, {"prompt_tokens": 3})

    def test_events_are_forwarded_to_the_renderer_hook(self):
        backend = scripted(
            [StreamEvent(kind="text", text="a"), StreamEvent(kind="text", text="b")]
        )
        agent = Agent(backend, PARAMS, Conversation())
        seen = []
        agent.send("hi", seen.append)
        self.assertEqual([e.text for e in seen], ["a", "b"])

    def test_second_turn_replays_previous_reasoning_to_the_backend(self):
        """The DeepSeek thinking-mode constraint, verified at the loop level."""
        backend = scripted(
            [
                StreamEvent(kind="reasoning", text="I will say hi."),
                StreamEvent(kind="text", text="hi"),
            ],
            [StreamEvent(kind="text", text="again")],
        )
        agent = Agent(backend, PARAMS, Conversation())
        agent.send("hello")
        agent.send("say it again")

        second_request = backend.requests[1]
        assistant_messages = [m for m in second_request if m["role"] == "assistant"]
        self.assertEqual(assistant_messages[0]["reasoning_content"], "I will say hi.")


class TestTransactionalTurn(unittest.TestCase):
    def test_rollback_discards_a_failed_turn(self):
        class ExplodingBackend:
            def stream(self, messages, params):
                yield StreamEvent(kind="text", text="partial")
                raise RuntimeError("connection dropped")

        agent = Agent(ExplodingBackend(), PARAMS, Conversation.with_system_prompt("sys"))
        checkpoint = agent.checkpoint()
        with self.assertRaises(RuntimeError):
            agent.send("hi")
        agent.rollback(checkpoint)
        self.assertEqual([m.role for m in agent.conversation], ["system"])


if __name__ == "__main__":
    unittest.main()
