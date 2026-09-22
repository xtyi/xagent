"""Where model settings and credentials come from.

Deliberately *outside* the agent: a finished `ModelConfig` is handed to a
backend, so nothing below the CLI reads files or environment variables. This
module is the one place that knows about TOML and `os.environ`.

Resolution order, per setting (first hit wins):

    CLI flag  >  environment variable  >  .xagent/config.toml  >  built-in default

The config file lives in the repo and is modeled on Codex's `config.toml`, so
provider blocks can be copied over nearly as-is. It holds an API key, so it is
**gitignored** -- only `.xagent/config.toml.example` is committed.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# `xagent/config.py` -> `xagent/` -> repo root, so the config file is found
# regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / ".xagent" / "config.toml"

DEFAULT_PROVIDER = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 120.0

ENV_API_KEYS = ("XAGENT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
ENV_BASE_URL = "XAGENT_BASE_URL"
ENV_MODEL = "XAGENT_MODEL"
ENV_PROVIDER = "XAGENT_PROVIDER"
ENV_CONFIG_PATH = "XAGENT_CONFIG"


class ConfigError(RuntimeError):
    """Raised when no usable configuration can be assembled."""


@dataclass(frozen=True)
class ModelConfig:
    """A finished, fully-resolved configuration. Every field has a value."""

    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    streaming: bool
    credential_source: str


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str


@dataclass(frozen=True)
class FileConfig:
    """What `.xagent/config.toml` may say. Absent keys stay `None`."""

    model_provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    providers: dict[str, ProviderConfig] = field(default_factory=dict)


def normalize_base_url(base: str) -> str:
    """Append `/v1` unless it is already there.

    Codex writes provider roots (`https://api.deepseek.com/`) while the
    OpenAI-compatible API lives under `/v1`. Normalizing once here means no
    call site has to know that.
    """
    trimmed = base.strip().rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed
    return f"{trimmed}/v1"


def load_config_file(path: Path = CONFIG_PATH) -> FileConfig:
    """Parse `.xagent/config.toml`. A missing file yields an empty config.

    A *malformed* file is an error rather than a silent skip: a typo in a
    config file should be loud, not something you debug by wondering why your
    settings are ignored.
    """
    if not path.is_file():
        return FileConfig()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    providers: dict[str, ProviderConfig] = {}
    for key, spec in (data.get("model_providers") or {}).items():
        base_url = spec.get("base_url") or ""
        if not base_url:
            raise ConfigError(f"{path}: provider [{key}] is missing `base_url`")
        providers[key] = ProviderConfig(
            name=spec.get("name") or key,
            base_url=normalize_base_url(base_url),
            api_key=spec.get("api_key") or "",
        )

    config = FileConfig(
        model_provider=data.get("model_provider"),
        model=data.get("model"),
        temperature=data.get("temperature"),
        max_tokens=data.get("max_tokens"),
        timeout=data.get("timeout"),
        providers=providers,
    )
    if config.model_provider and config.model_provider not in config.providers:
        known = ", ".join(sorted(config.providers)) or "none"
        raise ConfigError(
            f"{path}: model_provider is [{config.model_provider}] "
            f"but defined providers are [{known}]"
        )
    return config


def resolve_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    streaming: bool = True,
    provider: str | None = None,
    config_path: Path | None = None,
) -> ModelConfig:
    """Collapse every source into one `ModelConfig`."""
    path = config_path or Path(os.environ.get(ENV_CONFIG_PATH) or CONFIG_PATH)
    file_config = load_config_file(path)

    provider_name = (
        provider
        or os.environ.get(ENV_PROVIDER)
        or file_config.model_provider
        or DEFAULT_PROVIDER
    )
    entry = file_config.providers.get(provider_name)

    key, source = api_key or "", "--api-key" if api_key else ""
    if not key:
        for env_name in ENV_API_KEYS:
            candidate = os.environ.get(env_name, "")
            if candidate:
                key, source = candidate, f"env {env_name}"
                break
    if not key and entry is not None and entry.api_key:
        key, source = entry.api_key, f"{path} [{provider_name}]"
    if not key:
        raise ConfigError(
            f"no API key found. Add [model_providers.{provider_name}] with an "
            f"`api_key` to {path}, or pass --api-key, or set XAGENT_API_KEY "
            f"(DEEPSEEK_API_KEY / OPENAI_API_KEY also work)."
        )

    if base_url:
        resolved_base = base_url
    elif os.environ.get(ENV_BASE_URL):
        resolved_base = os.environ[ENV_BASE_URL]
    elif entry is not None:
        resolved_base = entry.base_url
    else:
        resolved_base = DEFAULT_BASE_URL

    def pick(explicit, from_file, default):
        if explicit is not None:
            return explicit
        return default if from_file is None else from_file

    return ModelConfig(
        base_url=normalize_base_url(resolved_base),
        api_key=key,
        model=model or os.environ.get(ENV_MODEL) or file_config.model or DEFAULT_MODEL,
        temperature=pick(temperature, file_config.temperature, DEFAULT_TEMPERATURE),
        max_tokens=pick(max_tokens, file_config.max_tokens, DEFAULT_MAX_TOKENS),
        timeout=pick(timeout, file_config.timeout, DEFAULT_TIMEOUT),
        streaming=streaming,
        credential_source=source,
    )
