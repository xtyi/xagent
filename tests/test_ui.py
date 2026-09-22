"""Renderer tests: the status line and out-of-band diagnostics."""

from io import StringIO

from xagent.ui import Renderer


def test_status_renders_pairs_on_a_single_line():
    out = StringIO()
    Renderer(out=out).status(
        [("model", "deepseek-flash"), ("thinking", "high"), ("stream", "on")]
    )
    text = out.getvalue()

    assert "model=deepseek-flash thinking=high stream=on" in text
    assert text.count("\n") == 1


def test_status_with_no_fields_is_still_one_line():
    out = StringIO()
    Renderer(out=out).status([])

    assert "[]" in out.getvalue()
    assert out.getvalue().count("\n") == 1


def test_diagnostic_goes_to_stderr_not_stdout():
    out, err = StringIO(), StringIO()
    renderer = Renderer(out=out, err=err)

    renderer.diagnostic("credential=env XAGENT_API_KEY")

    assert out.getvalue() == ""
    assert "credential=env XAGENT_API_KEY" in err.getvalue()
