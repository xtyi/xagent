"""Config resolution tests: precedence rules and `/v1` normalization.

Also a tour of two pytest fixtures worth knowing: `monkeypatch` for environment
variables and `tmp_path` for throwaway files (no manual cleanup, and the real
`~/.codex/config.toml` is never touched).
"""

import pytest

from xagent.config import (
    ConfigError,
    load_codex_credential,
    normalize_base_url,
    resolve_config,
)

API_KEY_ENV_VARS = ("XAGENT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
CODEX_TOML = (
    "[model_providers.deepseek]\n"
    'base_url = "https://api.deepseek.com/"\n'
    'experimental_bearer_token = "tok-from-codex"\n'
)


@pytest.fixture
def no_api_key_env(monkeypatch):
    """Guarantee the ambient environment cannot supply a key."""
    for name in API_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.deepseek.com/", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
        ("  https://example.com/v1/  ", "https://example.com/v1"),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_explicit_api_key_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("XAGENT_API_KEY", "from-env")

    config = resolve_config(api_key="from-flag")

    assert config.api_key == "from-flag"
    assert config.credential_source == "--api-key"


def test_environment_api_key_is_used_when_no_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("XAGENT_API_KEY", "from-env")
    monkeypatch.delenv("XAGENT_BASE_URL", raising=False)

    config = resolve_config(codex_config_path=tmp_path / "missing.toml")

    assert config.credential_source == "env XAGENT_API_KEY"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert (config.temperature, config.max_tokens) == (0.0, 2048)


def test_codex_config_is_the_last_resort(no_api_key_env, tmp_path):
    codex_config = tmp_path / "config.toml"
    codex_config.write_text(CODEX_TOML, encoding="utf-8")

    config = resolve_config(codex_config_path=codex_config)

    assert config.api_key == "tok-from-codex"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.credential_source.endswith("[deepseek]")


def test_missing_credentials_raise_with_guidance(no_api_key_env, tmp_path):
    with pytest.raises(ConfigError, match="no API key found"):
        resolve_config(codex_config_path=tmp_path / "missing.toml")


def test_load_codex_credential_ignores_a_missing_file(tmp_path):
    assert load_codex_credential("deepseek", tmp_path / "nope.toml") is None
