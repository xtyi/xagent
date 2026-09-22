"""Where model settings and credentials come from.

Deliberately *outside* the agent: a finished `ModelConfig` is handed to a
backend, so nothing below the CLI reads environment variables or files. When
this project later grows a config file of its own, only this module changes.

Credential resolution order (first hit wins):

    --api-key  >  XAGENT_API_KEY  >  DEEPSEEK_API_KEY / OPENAI_API_KEY
               >  ~/.codex/config.toml

The last one exists purely for convenience on this machine: reusing the
provider block Codex already has configured. The token itself is never logged;
only its *source* is reported.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROVIDER = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 2048

CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"

ENV_API_KEYS = ("XAGENT_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
ENV_BASE_URL = "XAGENT_BASE_URL"
ENV_MODEL = "XAGENT_MODEL"
ENV_PROVIDER = "XAGENT_PROVIDER"


class ConfigError(RuntimeError):
    """Raised when no usable configuration can be assembled."""


@dataclass(frozen=True)
class ModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    streaming: bool
    credential_source: str


def normalize_base_url(base: str) -> str:
    """Append `/v1` unless it is already there.

    Codex stores the provider root (`https://api.deepseek.com/`), while the
    OpenAI-compatible API lives under `/v1`. Rather than duplicating that
    knowledge in every call site, we normalize once, here.
    """
    trimmed = base.strip().rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed
    return f"{trimmed}/v1"


def load_codex_credential(
    provider: str, path: Path = CODEX_CONFIG_PATH
) -> tuple[str, str] | None:
    """Return `(base_url, api_key)` from Codex's own config, if present."""
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    spec = (data.get("model_providers") or {}).get(provider) or {}
    api_key = spec.get("experimental_bearer_token") or ""
    if not api_key:
        return None
    return normalize_base_url(spec.get("base_url") or DEFAULT_BASE_URL), api_key


def resolve_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float = 120.0,
    streaming: bool = True,
    provider: str | None = None,
    codex_config_path: Path = CODEX_CONFIG_PATH,
) -> ModelConfig:
    provider_name = provider or os.environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER
    codex_credential = load_codex_credential(provider_name, codex_config_path)

    resolved_key = ""
    source = ""
    from_codex = False

    if api_key:
        resolved_key, source = api_key, "--api-key"
    if not resolved_key:
        for env_name in ENV_API_KEYS:
            candidate = os.environ.get(env_name, "")
            if candidate:
                resolved_key, source = candidate, f"env {env_name}"
                break
    if not resolved_key and codex_credential is not None:
        resolved_key = codex_credential[1]
        source = f"{codex_config_path} [{provider_name}]"
        from_codex = True

    if not resolved_key:
        raise ConfigError(
            "no API key found. Pass --api-key, set XAGENT_API_KEY "
            "(or DEEPSEEK_API_KEY / OPENAI_API_KEY), or use --mock "
            "for an offline demo."
        )

    if base_url:
        resolved_base = base_url
    elif os.environ.get(ENV_BASE_URL):
        resolved_base = os.environ[ENV_BASE_URL]
    elif from_codex and codex_credential is not None:
        resolved_base = codex_credential[0]
    else:
        resolved_base = DEFAULT_BASE_URL

    return ModelConfig(
        base_url=normalize_base_url(resolved_base),
        api_key=resolved_key,
        model=model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL,
        temperature=DEFAULT_TEMPERATURE if temperature is None else temperature,
        max_tokens=DEFAULT_MAX_TOKENS if max_tokens is None else max_tokens,
        timeout=timeout,
        streaming=streaming,
        credential_source=source,
    )
