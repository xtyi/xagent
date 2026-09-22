"""Transport-layer tests: SSE parsing and chunk -> event translation.

Pure functions only: no sockets, no threads, no sleeping.
"""

import pytest

from xagent.backends.openai_compat import (
    chunk_to_events,
    iter_sse_payloads,
    parse_chunks,
    response_to_events,
)


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param(
            [b'data: {"a": 1}\n', b"\n", b'data: {"a": 2}\n', b"\n"],
            ['{"a": 1}', '{"a": 2}'],
            id="two-single-line-events",
        ),
        pytest.param(
            [b": keep-alive\n", b"event: message\n", b"data: hello\n", b"\n"],
            ["hello"],
            id="drops-comments-and-non-data-fields",
        ),
        pytest.param(
            [b"data: part1\n", b"data: part2\n", b"\n"],
            ["part1\npart2"],
            id="joins-multiline-data",
        ),
        pytest.param(["data: x\r\n", "\r\n"], ["x"], id="accepts-crlf-and-str"),
        pytest.param([b"data: tail\n"], ["tail"], id="keeps-unterminated-final-event"),
    ],
)
def test_iter_sse_payloads(lines, expected):
    assert list(iter_sse_payloads(lines)) == expected


def test_parse_chunks_stops_at_done_sentinel():
    lines = [b'data: {"i": 1}\n', b"\n", b"data: [DONE]\n", b"\n", b'data: {"i": 2}\n']
    assert [chunk["i"] for chunk in parse_chunks(lines)] == [1]


def test_parse_chunks_skips_empty_payloads():
    lines = [b"data:\n", b"\n", b'data: {"i": 3}\n', b"\n"]
    assert [chunk["i"] for chunk in parse_chunks(lines)] == [3]


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        pytest.param(
            {"reasoning_content": "think", "content": "say"},
            [("reasoning", "think"), ("text", "say")],
            id="reasoning-and-text-are-separate-events",
        ),
        pytest.param(
            {"reasoning_content": None, "content": None},
            [],
            id="null-fields-produce-no-events",
        ),
        pytest.param({"content": "only"}, [("text", "only")], id="text-only-delta"),
    ],
)
def test_chunk_to_events_maps_deltas(delta, expected):
    chunk = {"choices": [{"delta": delta}]}
    assert [(event.kind, event.text) for event in chunk_to_events(chunk)] == expected


def test_usage_only_chunk_emits_usage_event():
    chunk = {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
    events = list(chunk_to_events(chunk))
    assert [event.kind for event in events] == ["usage"]
    assert events[0].usage["completion_tokens"] == 7


def test_non_streaming_response_maps_to_the_same_events():
    body = {
        "choices": [{"message": {"content": "hi", "reasoning_content": "hmm"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    assert [event.kind for event in response_to_events(body)] == [
        "reasoning",
        "text",
        "usage",
    ]
