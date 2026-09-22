"""Transport-layer tests: SSE parsing and chunk -> event translation.

These are pure-function tests: no sockets, no threads, no sleeping.
"""

import unittest

from xagent.backends.openai_compat import (
    chunk_to_events,
    iter_sse_payloads,
    parse_chunks,
    response_to_events,
)


class TestIterSSEPayloads(unittest.TestCase):
    def test_single_line_events(self):
        lines = [b'data: {"a": 1}\n', b"\n", b'data: {"a": 2}\n', b"\n"]
        self.assertEqual(list(iter_sse_payloads(lines)), ['{"a": 1}', '{"a": 2}'])

    def test_ignores_comments_and_other_fields(self):
        lines = [b": keep-alive\n", b"event: message\n", b"data: hello\n", b"\n"]
        self.assertEqual(list(iter_sse_payloads(lines)), ["hello"])

    def test_joins_multiline_data(self):
        lines = [b"data: part1\n", b"data: part2\n", b"\n"]
        self.assertEqual(list(iter_sse_payloads(lines)), ["part1\npart2"])

    def test_handles_carriage_returns_and_str_input(self):
        lines = ["data: x\r\n", "\r\n"]
        self.assertEqual(list(iter_sse_payloads(lines)), ["x"])

    def test_trailing_event_without_blank_line(self):
        self.assertEqual(list(iter_sse_payloads([b"data: tail\n"])), ["tail"])


class TestParseChunks(unittest.TestCase):
    def test_stops_at_done_sentinel(self):
        lines = [b'data: {"i": 1}\n', b"\n", b"data: [DONE]\n", b"\n", b'data: {"i": 2}\n']
        self.assertEqual([c["i"] for c in parse_chunks(lines)], [1])

    def test_skips_empty_payloads(self):
        lines = [b"data:\n", b"\n", b'data: {"i": 3}\n', b"\n"]
        self.assertEqual([c["i"] for c in parse_chunks(lines)], [3])


class TestChunkToEvents(unittest.TestCase):
    def test_reasoning_and_text_are_separate_events(self):
        chunk = {"choices": [{"delta": {"reasoning_content": "think", "content": "say"}}]}
        events = list(chunk_to_events(chunk))
        self.assertEqual([(e.kind, e.text) for e in events], [("reasoning", "think"), ("text", "say")])

    def test_null_fields_produce_no_events(self):
        chunk = {"choices": [{"delta": {"reasoning_content": None, "content": None}}]}
        self.assertEqual(list(chunk_to_events(chunk)), [])

    def test_usage_chunk_emits_usage_event(self):
        chunk = {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
        events = list(chunk_to_events(chunk))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "usage")
        self.assertEqual(events[0].usage["completion_tokens"], 7)


class TestResponseToEvents(unittest.TestCase):
    def test_non_streaming_response_maps_to_same_events(self):
        body = {
            "choices": [{"message": {"content": "hi", "reasoning_content": "hmm"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
        self.assertEqual(
            [e.kind for e in response_to_events(body)],
            ["reasoning", "text", "usage"],
        )


if __name__ == "__main__":
    unittest.main()
