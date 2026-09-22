"""OpenAI-compatible `/chat/completions` transport.

Scope is intentionally narrow: build the HTTP request, turn the response bytes
into SSE payloads, turn payloads into `StreamEvent`s. It knows nothing about
agents, tools, or policy.

Streaming vs non-streaming is a *transport* choice, so both modes are hidden
behind the same `stream()` method: nothing above this file has to care which
one is in use. That is what makes `--no-stream` a one-line change later.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterable, Iterator, Sequence

from .base import BackendError, ModelParams, StreamEvent

SSE_DONE = "[DONE]"


def iter_sse_payloads(lines: Iterable[bytes | str]) -> Iterator[str]:
    """Yield the `data` payload of each Server-Sent Event.

    Implements just enough of the SSE spec to be correct rather than lucky:
    `data:` lines accumulate until a blank line terminates the event,
    `:`-prefixed lines are comments, every other field is ignored.
    """
    buffered: list[str] = []
    for raw in lines:
        if isinstance(raw, (bytes, bytearray)):
            line = raw.decode("utf-8", errors="replace")
        else:
            line = raw
        line = line.rstrip("\r\n")
        if not line:
            if buffered:
                yield "\n".join(buffered)
                buffered.clear()
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field == "data":
            buffered.append(value[1:] if value.startswith(" ") else value)
    if buffered:
        yield "\n".join(buffered)


def parse_chunks(lines: Iterable[bytes | str]) -> Iterator[dict[str, Any]]:
    """SSE payloads -> JSON chunks, stopping at the `[DONE]` sentinel."""
    for payload in iter_sse_payloads(lines):
        if payload.strip() == SSE_DONE:
            return
        if not payload.strip():
            continue
        yield json.loads(payload)


def chunk_to_events(chunk: dict[str, Any]) -> Iterator[StreamEvent]:
    """One streaming chunk -> zero or more events."""
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        reasoning = delta.get("reasoning_content")
        if reasoning:
            yield StreamEvent(kind="reasoning", text=reasoning)
        text = delta.get("content")
        if text:
            yield StreamEvent(kind="text", text=text)
        # Step 2 hooks in here: tool-call fragments arrive as
        # delta["tool_calls"], split across chunks by `index`.
    if chunk.get("usage"):
        yield StreamEvent(kind="usage", usage=chunk["usage"])


def response_to_events(body: dict[str, Any]) -> Iterator[StreamEvent]:
    """One non-streaming response -> the same events a stream would produce."""
    for choice in body.get("choices") or []:
        message = choice.get("message") or {}
        if message.get("reasoning_content"):
            yield StreamEvent(kind="reasoning", text=message["reasoning_content"])
        if message.get("content"):
            yield StreamEvent(kind="text", text=message["content"])
    if body.get("usage"):
        yield StreamEvent(kind="usage", usage=body["usage"])


class OpenAICompatBackend:
    """Talks to any `/chat/completions` endpoint that speaks OpenAI's schema."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        streaming: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.streaming = streaming
        self.extra_headers = dict(extra_headers or {})

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def build_payload(
        self, messages: Sequence[dict[str, Any]], params: ModelParams
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": params.model,
            "messages": list(messages),
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "stream": self.streaming,
        }
        if self.streaming:
            # Without this the final chunk carries no token counts.
            payload["stream_options"] = {"include_usage": True}
        if params.reasoning_effort:
            # DeepSeek accepts the OpenAI-standard name `reasoning_effort` and
            # honours `none` as "do not think". Measured in probes/001.
            payload["reasoning_effort"] = params.reasoning_effort
        return payload

    def stream(
        self, messages: Sequence[dict[str, Any]], params: ModelParams
    ) -> Iterator[StreamEvent]:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(self.build_payload(messages, params)).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                **self.extra_headers,
            },
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise BackendError(f"HTTP {exc.code} from {self.endpoint}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"cannot reach {self.endpoint}: {exc.reason}") from exc

        with response:
            if self.streaming:
                for chunk in parse_chunks(response):
                    yield from chunk_to_events(chunk)
            else:
                body = json.loads(response.read().decode("utf-8"))
                yield from response_to_events(body)
