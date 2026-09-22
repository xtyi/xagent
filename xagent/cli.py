"""Command line wiring: config -> backend -> agent -> renderer.

This is the only module that knows about all the others, and the only one that
talks to a human. Everything it builds is a plain library object, so the same
agent can be driven from a test or, later, a TUI.
"""

from __future__ import annotations

import argparse
import json

from .agent import Agent
from .backends.base import Backend, BackendError, ModelParams
from .backends.mock import MockBackend
from .backends.openai_compat import OpenAICompatBackend
from .config import REASONING_EFFORTS, ConfigError, resolve_config
from .messages import Conversation
from .ui import BOLD, DIM, RESET, Renderer

DEFAULT_SYSTEM_PROMPT = (
    "You are xagent, a minimal coding agent running in a terminal. "
    "Be concise and precise. Say so when you are unsure rather than guessing."
)

HELP_TEXT = """commands:
  /help       show this help
  /status     show the current session settings
  /reset      drop the conversation history (keeps the system prompt)
  /usage      show token usage of the last turn
  /reasoning  toggle displaying the model's thinking
  /exit       quit"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xagent",
        description="A from-scratch, teaching-oriented code agent (Step 1: chat loop).",
    )
    parser.add_argument("--model", help="model name (default: deepseek-flash)")
    parser.add_argument("--base-url", help="OpenAI-compatible API root")
    parser.add_argument("--api-key", help="API key; overrides environment lookup")
    parser.add_argument("--system", help="override the system prompt")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="thinking effort: `none` disables thinking; else low/medium/high/max",
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        help="print the model's thinking stream in dim text",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="use one non-streaming request instead of SSE",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="offline echo backend: no network, no credentials",
    )
    parser.add_argument("--once", metavar="PROMPT", help="run a single turn and exit")
    return parser


def status_fields(
    model: str, reasoning_effort: str | None, streaming: bool
) -> list[tuple[str, str]]:
    """The per-session settings shown in the status line.

    Kept as (key, value) pairs rather than a fixed dataclass so later session
    settings -- permissions, workspace, ... -- can join the line without
    reworking the renderer.
    """
    return [
        ("model", model),
        ("thinking", reasoning_effort or "default"),
        ("stream", "on" if streaming else "off"),
    ]


def build_agent(
    args: argparse.Namespace, renderer: Renderer
) -> tuple[Agent, list[tuple[str, str]]]:
    system_prompt = DEFAULT_SYSTEM_PROMPT if args.system is None else args.system
    conversation = Conversation.with_system_prompt(system_prompt)

    if args.mock:
        backend: Backend = MockBackend.echo()
        model = args.model or "mock"
        temperature = 0.0 if args.temperature is None else args.temperature
        max_tokens = 256 if args.max_tokens is None else args.max_tokens
        reasoning_effort = args.reasoning_effort
        streaming = not args.no_stream
        renderer.diagnostic(f"{DIM}[config] backend=mock (offline, no network){RESET}")
    else:
        config = resolve_config(
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
            streaming=not args.no_stream,
        )
        # Credentials are out-of-band: stderr, and never the key itself.
        renderer.diagnostic(
            f"{DIM}[config] base_url={config.base_url} "
            f"credential={config.credential_source}{RESET}"
        )
        backend = OpenAICompatBackend(
            config.base_url,
            config.api_key,
            timeout=config.timeout,
            streaming=config.streaming,
        )
        model, temperature, max_tokens = config.model, config.temperature, config.max_tokens
        reasoning_effort, streaming = config.reasoning_effort, config.streaming

    params = ModelParams(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    agent = Agent(backend, params, conversation)
    return agent, status_fields(model, reasoning_effort, streaming)


def run_turn(agent: Agent, renderer: Renderer, text: str) -> None:
    """Render one turn, treating it as a transaction: fail => no history change."""
    checkpoint = agent.checkpoint()
    renderer.begin_turn()
    try:
        agent.send(text, renderer.on_event)
    except (BackendError, KeyboardInterrupt) as exc:
        agent.rollback(checkpoint)
        renderer.end_turn()
        renderer.error(str(exc) or "interrupted")
        return
    renderer.end_turn()


def handle_command(
    raw: str, agent: Agent, renderer: Renderer, fields: list[tuple[str, str]]
) -> str:
    command = raw.split()[0].lower()
    if command in ("/exit", "/quit"):
        return "exit"
    if command == "/help":
        renderer.note(HELP_TEXT)
    elif command == "/status":
        renderer.status(fields)
    elif command == "/reset":
        agent.conversation.clear()
        renderer.note("history cleared")
    elif command == "/usage":
        usage = agent.last_usage if agent.last_usage is not None else "none recorded yet"
        renderer.note(json.dumps(usage) if isinstance(usage, dict) else usage)
    elif command == "/reasoning":
        renderer.show_reasoning = not renderer.show_reasoning
        renderer.note(f"show_reasoning = {renderer.show_reasoning}")
    else:
        renderer.note(f"unknown command: {command} (try /help)")
    return "continue"


def repl(agent: Agent, renderer: Renderer, fields: list[tuple[str, str]]) -> int:
    renderer.note(f"{DIM}xagent -- /help for commands, /exit to quit{RESET}")
    while True:
        try:
            line = input(f"{BOLD}you>{RESET} ")
        except (EOFError, KeyboardInterrupt):
            renderer.note("")
            return 0
        text = line.strip()
        if not text:
            continue
        if text.startswith("/"):
            if handle_command(text, agent, renderer, fields) == "exit":
                return 0
            continue
        run_turn(agent, renderer, text)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    renderer = Renderer(show_reasoning=args.show_reasoning)
    try:
        agent, fields = build_agent(args, renderer)
    except ConfigError as exc:
        renderer.error(str(exc))
        return 2
    renderer.status(fields)
    if args.once is not None:
        run_turn(agent, renderer, args.once)
        return 0
    return repl(agent, renderer, fields)
