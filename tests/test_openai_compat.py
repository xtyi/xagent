"""Transport tests for the OpenAI-compatible request payload.

Pure functions / plain objects only: no sockets, no threads.
"""

from xagent.backends.base import ModelParams
from xagent.backends.openai_compat import OpenAICompatBackend


def backend(**kwargs) -> OpenAICompatBackend:
    return OpenAICompatBackend("https://example.com/v1", "key", **kwargs)


def test_endpoint_joins_base_and_path():
    assert backend().endpoint == "https://example.com/v1/chat/completions"


def test_reasoning_effort_is_sent_when_set():
    payload = backend().build_payload(
        [{"role": "user", "content": "hi"}],
        ModelParams(model="m", reasoning_effort="high"),
    )

    assert payload["reasoning_effort"] == "high"


def test_reasoning_effort_is_omitted_by_default():
    payload = backend().build_payload(
        [{"role": "user", "content": "hi"}], ModelParams(model="m")
    )

    assert "reasoning_effort" not in payload


def test_reasoning_effort_none_is_sent_verbatim():
    payload = backend().build_payload([], ModelParams(model="m", reasoning_effort="none"))

    assert payload["reasoning_effort"] == "none"
