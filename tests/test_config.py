"""Config resolution tests: file parsing, precedence, and error paths.

Also a tour of two pytest fixtures worth knowing: `monkeypatch` for environment
variables and `tmp_path` for throwaway files.

No test reads the real `~/.xagent/config.toml`: each one passes an explicit
`config_path` (or sets `XAGENT_CONFIG`), so the suite does not depend on
whatever key happens to be on this machine.
"""

from pathlib import Path

import pytest

from xagent.config import (
    CONFIG_DIR,
    CONFIG_PATH,
    ConfigError,
    FileConfig,
    load_config_file,
    normalize_base_url,
    resolve_config,
)

AMBIENT_ENV_VARS = (
    "XAGENT_API_KEY",
    "XAGENT_BASE_URL",
    "XAGENT_MODEL",
    "XAGENT_PROVIDER",
    "XAGENT_CONFIG",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
)

CONFIG_TOML = """\
model_provider = "deepseek"
model = "deepseek-flash"
temperature = 0.3
max_tokens = 128
timeout = 30.0

[model_providers.deepseek]
name = "deepseek"
base_url = "https://api.deepseek.com/"
api_key = "key-from-file"
"""

TWO_PROVIDER_TOML = """\
model_provider = "deepseek"

[model_providers.deepseek]
base_url = "https://api.deepseek.com/"
api_key = "deepseek-key"

[model_providers.openai]
base_url = "https://api.openai.com/v1"
api_key = "openai-key"
"""


@pytest.fixture
def clean_env(monkeypatch):
    """Make the ambient environment irrelevant to the test."""
    for name in AMBIENT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TOML, encoding="utf-8")
    return path


@pytest.fixture
def absent_file(tmp_path):
    return tmp_path / "nope.toml"


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


def test_default_config_path_lives_in_the_home_directory():
    assert CONFIG_DIR == Path.home() / ".xagent"
    assert CONFIG_PATH == CONFIG_DIR / "config.toml"


def test_missing_file_is_an_empty_config(absent_file):
    assert load_config_file(absent_file) == FileConfig()


def test_provider_block_is_parsed_and_normalized(config_file):
    file_config = load_config_file(config_file)

    assert file_config.model_provider == "deepseek"
    assert file_config.temperature == 0.3
    assert file_config.max_tokens == 128
    assert file_config.timeout == 30.0
    provider = file_config.providers["deepseek"]
    assert provider.api_key == "key-from-file"
    assert provider.base_url == "https://api.deepseek.com/v1"
    assert provider.name == "deepseek"


def test_malformed_toml_is_loud(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("model_provider = \n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config_file(path)


def test_provider_without_base_url_is_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[model_providers.deepseek]\napi_key = "k"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="missing"):
        load_config_file(path)


def test_model_provider_must_be_defined_in_the_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'model_provider = "deepseel"\n'
        '[model_providers.deepseek]\nbase_url = "https://api.deepseek.com/"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="defined providers"):
        load_config_file(path)


def test_file_supplies_every_setting(clean_env, config_file):
    config = resolve_config(config_path=config_file)

    assert config.api_key == "key-from-file"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.model == "deepseek-flash"
    assert config.temperature == 0.3
    assert config.max_tokens == 128
    assert config.timeout == 30.0
    assert config.credential_source.endswith("[deepseek]")


def test_built_in_defaults_apply_without_a_config_file(clean_env, absent_file):
    config = resolve_config(api_key="from-flag", config_path=absent_file)

    assert config.model == "deepseek-flash"
    assert config.temperature == 0.0
    assert config.max_tokens == 2048
    assert config.timeout == 120.0
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.credential_source == "--api-key"


def test_cli_flag_beats_environment(clean_env, monkeypatch, config_file):
    monkeypatch.setenv("XAGENT_API_KEY", "from-env")

    config = resolve_config(api_key="from-flag", config_path=config_file)

    assert config.api_key == "from-flag"
    assert config.credential_source == "--api-key"


def test_environment_beats_file(clean_env, monkeypatch, config_file):
    monkeypatch.setenv("XAGENT_API_KEY", "from-env")

    config = resolve_config(config_path=config_file)

    assert config.api_key == "from-env"
    assert config.credential_source == "env XAGENT_API_KEY"


@pytest.mark.parametrize(
    ("env_name", "env_value", "attribute"),
    [
        ("XAGENT_BASE_URL", "https://example.com/v1", "base_url"),
        ("XAGENT_MODEL", "some-other-model", "model"),
    ],
)
def test_environment_overrides_file_settings(
    clean_env, monkeypatch, config_file, env_name, env_value, attribute
):
    monkeypatch.setenv(env_name, env_value)

    config = resolve_config(config_path=config_file)

    assert getattr(config, attribute) == env_value


def test_config_path_environment_variable(clean_env, monkeypatch, config_file):
    monkeypatch.setenv("XAGENT_CONFIG", str(config_file))

    config = resolve_config()

    assert config.api_key == "key-from-file"


def test_provider_argument_selects_another_block(clean_env, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TWO_PROVIDER_TOML, encoding="utf-8")

    config = resolve_config(provider="openai", config_path=path)

    assert config.base_url == "https://api.openai.com/v1"
    assert config.api_key == "openai-key"


def test_missing_credentials_raise_with_guidance(clean_env, absent_file):
    with pytest.raises(ConfigError, match="no API key found"):
        resolve_config(config_path=absent_file)
