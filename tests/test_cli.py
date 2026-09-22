"""CLI wiring tests: the status fields and the reasoning-effort flag."""

import pytest

from xagent.cli import build_parser, status_fields


def test_status_fields_show_model_thinking_and_streaming():
    assert status_fields("deepseek-flash", "high", True) == [
        ("model", "deepseek-flash"),
        ("thinking", "high"),
        ("stream", "on"),
    ]


def test_status_fields_label_an_unset_effort_as_default():
    fields = dict(status_fields("m", None, False))

    assert fields["thinking"] == "default"
    assert fields["stream"] == "off"


@pytest.mark.parametrize("level", ["none", "low", "medium", "high", "max"])
def test_parser_accepts_known_reasoning_efforts(level):
    args = build_parser().parse_args(["--reasoning-effort", level])

    assert args.reasoning_effort == level


def test_parser_rejects_an_unknown_reasoning_effort():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--reasoning-effort", "off"])
