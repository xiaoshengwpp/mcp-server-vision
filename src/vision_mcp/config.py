"""
Vision MCP Server Configuration Module.

Provides centralized configuration management with support for:
- Environment variable overrides (prefix: VISION_MCP_)
- YAML configuration file loading
- Multi-provider configuration (OpenAI / Anthropic / Ollama)
- .env file support with ${VAR} substitution
- Security restrictions (file size limits, path whitelists)

Usage:
    from vision_mcp.config import get_config
    config = get_config()
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENV_PREFIX = "VISION_MCP_"
_DEFAULT_ENV_FILE = ".env"

_SIMPLE_CONFIG_YAML_PATHS = (
    "config.yaml",
    "config.yml",
    "vision_mcp.yaml",
    "vision_mcp.yml",
)


# ---------------------------------------------------------------------------
# Provider Models
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Configuration for a single vision provider."""

    name: str  # unique identifier, e.g. "my-openai", "dashscope"
    type: str  # "openai", "anthropic", or "ollama"
    base_url: str = ""  # API endpoint URL (required for openai/ollama)
    api_key: str = ""  # API key (not required for ollama)
    model: str = ""  # model identifier
    max_tokens: int = 2000  # max output tokens for the model
    is_default: bool = False  # whether this is the default provider

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.type = self.type.strip().lower()
        self.base_url = self.base_url.strip().rstrip("/")
        self.api_key = self.api_key.strip()
        self.model = self.model.strip()

        if self.type not in ("openai", "anthropic", "ollama"):
            raise ValueError(f"Provider type must be 'openai', 'anthropic', or 'ollama', got '{self.type}'")
        if self.type in ("openai", "ollama") and not self.base_url:
            raise ValueError(f"Provider '{self.name}' (type={self.type}) must have a base_url")
        if not self.model:
            raise ValueError(f"Provider '{self.name}' must have a model")


@dataclass
class SimpleConfig:
    """
    Flexible configuration loaded from YAML and environment variables.

    Designed for use by ``server.py`` — supports user-defined providers
    with custom URLs, API keys, and models.

    Loading priority (highest first):
      1. Environment variables (single provider mode)
      2. ``.env`` file
      3. YAML config file
      4. Defaults
    """

    # Provider list (user-defined)
    providers: list[ProviderConfig] = field(default_factory=list)

    # API Settings
    api_timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 2.0
    max_concurrent_requests: int = 5

    # Security Limits
    max_image_size_mb: float = 20.0
    max_video_size_mb: float = 2048.0
    max_video_duration_minutes: float = 120.0
    max_image_pixels: int = 16_000_000

    # Paths
    allowed_paths: list[str] = field(default_factory=list)

    # Blocked domains (SSRF)
    blocked_domains: list[str] = field(default_factory=lambda: [
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "169.254.169.254", "metadata.google.internal", "100.100.100.200",
    ])

    # Logging & Server
    log_level: str = "INFO"
    transport: str = "stdio"

    def __post_init__(self) -> None:
        if not self.allowed_paths:
            self.allowed_paths = [
                str(Path(os.path.expanduser("~"))),
                "/tmp",
            ]
        self._normalize()

    def _normalize(self) -> None:
        self.allowed_paths = [
            str(Path(p).expanduser().resolve()) for p in self.allowed_paths
        ]

    def get_default_provider(self) -> ProviderConfig | None:
        """Return the default provider, or the first one if none is marked as default."""
        if not self.providers:
            return None
        for p in self.providers:
            if p.is_default:
                return p
        return self.providers[0]

    def get_provider_by_name(self, name: str) -> ProviderConfig | None:
        """Return a provider by name, or None if not found."""
        for p in self.providers:
            if p.name == name:
                return p
        return None


# ---- SimpleConfig singleton ----

_simple_config: SimpleConfig | None = None


def _find_simple_config_yaml() -> Path | None:
    """Find the YAML config file path."""
    env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p
        print(
            f"[vision_mcp] WARNING: VISION_MCP_CONFIG points to non-existent file: {p}",
            file=sys.stderr,
        )
        return None
    for candidate in _SIMPLE_CONFIG_YAML_PATHS:
        p = Path(candidate).expanduser()
        if p.is_absolute() and p.is_file():
            return p
        rel = Path.cwd() / p
        if rel.is_file():
            return rel
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")))
    xdg_file = xdg / "vision_mcp" / "config.yaml"
    if xdg_file.is_file():
        return xdg_file
    return None


def _load_simple_config(yaml_path: Path | None = None) -> SimpleConfig:
    """Load SimpleConfig from .env → YAML → env vars (ascending priority).

    .env is loaded first so that YAML values using ``${VAR}`` syntax
    can be resolved against both .env and system environment variables.
    """
    config = SimpleConfig()

    # 1. Load .env into os.environ (lowest priority, uses setdefault)
    _apply_dotenv_to_simple_config(config)

    # 2. Load from YAML (with ${VAR} substitution from os.environ)
    if yaml_path is None:
        yaml_path = _find_simple_config_yaml()
    if yaml_path is not None:
        _apply_yaml_to_simple_config(config, yaml_path)

    # 3. Load from environment variables (highest priority)
    _apply_env_to_simple_config(config)

    config._normalize()
    return config


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${VAR}`` references in strings using os.environ.

    - ``${VAR}`` → value of os.environ["VAR"], or "" if not set
    - Non-string values are returned as-is
    - Lists and dicts are processed recursively
    """
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return re.sub(r'\$\{(\w+)\}', _replace, value)
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    return value


def _apply_yaml_to_simple_config(config: SimpleConfig, path: Path) -> None:
    """Apply YAML config file values to SimpleConfig."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return

    # Resolve ${VAR} references in all values
    data = _resolve_env_vars(data)

    _float_keys = {
        "api_timeout", "retry_delay", "max_image_size_mb",
        "max_video_size_mb", "max_video_duration_minutes",
    }
    _int_keys = {"max_retries", "max_image_pixels"}
    _str_keys = {"log_level", "transport"}

    for key in _str_keys:
        if key in data and data[key] is not None:
            setattr(config, key, str(data[key]))
    for key in _float_keys:
        if key in data and data[key] is not None:
            try:
                setattr(config, key, float(data[key]))
            except (ValueError, TypeError):
                pass
    for key in _int_keys:
        if key in data and data[key] is not None:
            try:
                setattr(config, key, int(data[key]))
            except (ValueError, TypeError):
                pass
    if "allowed_paths" in data and isinstance(data["allowed_paths"], list):
        # Merge with defaults (~ and /tmp always included) to prevent users
        # from accidentally locking themselves out of common directories.
        home = str(Path(os.path.expanduser("~")))
        yaml_paths = [str(p) for p in data["allowed_paths"]]
        merged = [home] + yaml_paths
        config.allowed_paths = merged
    if "blocked_domains" in data and isinstance(data["blocked_domains"], list):
        config.blocked_domains = [str(d) for d in data["blocked_domains"]]

    # Parse providers list
    if "providers" in data and isinstance(data["providers"], list):
        config.providers = []
        for p_data in data["providers"]:
            if not isinstance(p_data, dict):
                continue
            try:
                provider = ProviderConfig(
                    name=p_data.get("name", ""),
                    type=p_data.get("type", "openai"),
                    base_url=p_data.get("base_url", ""),
                    api_key=p_data.get("api_key", ""),
                    model=p_data.get("model", ""),
                    max_tokens=p_data.get("max_tokens", 2000),
                    is_default=p_data.get("is_default", False),
                )
                config.providers.append(provider)
            except ValueError as e:
                print(f"[vision_mcp] WARNING: Skipping invalid provider: {e}", file=sys.stderr)


def _apply_dotenv_to_simple_config(config: SimpleConfig) -> None:
    """Load .env file values into os.environ (setdefault — won't override)."""
    dotenv_path = None
    for candidate in [Path.cwd() / ".env", Path.cwd() / ".." / ".env"]:
        if candidate.is_file():
            dotenv_path = candidate
            break
    if dotenv_path is None:
        return
    try:
        with open(dotenv_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and value:
                    os.environ.setdefault(key, value)
    except OSError:
        pass


def _apply_env_to_simple_config(config: SimpleConfig) -> None:
    """Apply environment variable overrides to SimpleConfig."""
    _env_mapping: list[tuple[str, str, type]] = [
        ("api_timeout", "VISION_MCP_API_TIMEOUT", float),
        ("max_retries", "VISION_MCP_MAX_RETRIES", int),
        ("retry_delay", "VISION_MCP_RETRY_DELAY", float),
        ("max_image_size_mb", "VISION_MCP_MAX_IMAGE_SIZE_MB", float),
        ("max_video_size_mb", "VISION_MCP_MAX_VIDEO_SIZE_MB", float),
        ("max_video_duration_minutes", "VISION_MCP_MAX_VIDEO_DURATION_MINUTES", float),
        ("max_image_pixels", "VISION_MCP_MAX_IMAGE_PIXELS", int),
        ("log_level", "VISION_MCP_LOG_LEVEL", str),
        ("transport", "VISION_MCP_TRANSPORT", str),
    ]
    for attr, env_var, converter in _env_mapping:
        val = os.environ.get(env_var)
        if val is not None and val != "":
            try:
                setattr(config, attr, converter(val))
            except (ValueError, TypeError):
                pass

    # Backward-compat: accept env vars without VISION_MCP_ prefix
    # Only apply unprefixed var if the prefixed var was NOT set
    _compat_mapping: list[tuple[str, str, str, type]] = [
        ("max_image_size_mb", "VISION_MCP_MAX_IMAGE_SIZE_MB", "MAX_IMAGE_SIZE_MB", float),
        ("max_video_size_mb", "VISION_MCP_MAX_VIDEO_SIZE_MB", "MAX_VIDEO_SIZE_MB", float),
        ("max_video_duration_minutes", "VISION_MCP_MAX_VIDEO_DURATION_MINUTES", "MAX_VIDEO_DURATION_MINUTES", float),
        ("max_image_pixels", "VISION_MCP_MAX_IMAGE_PIXELS", "MAX_IMAGE_PIXELS", int),
    ]
    for attr, prefixed_var, compat_var, converter in _compat_mapping:
        if os.environ.get(prefixed_var) is None:  # prefixed var not set
            val = os.environ.get(compat_var)
            if val is not None and val != "":
                try:
                    setattr(config, attr, converter(val))
                except (ValueError, TypeError):
                    pass

    # Support single provider via environment variables
    provider_type = os.environ.get("VISION_MCP_PROVIDER_TYPE", "").strip().lower()
    if provider_type:
        try:
            provider = ProviderConfig(
                name=os.environ.get("VISION_MCP_PROVIDER_NAME", "default").strip(),
                type=provider_type,
                base_url=os.environ.get("VISION_MCP_PROVIDER_BASE_URL", "").strip(),
                api_key=os.environ.get("VISION_MCP_PROVIDER_API_KEY", "").strip(),
                model=os.environ.get("VISION_MCP_PROVIDER_MODEL", "").strip(),
                max_tokens=int(os.environ.get("VISION_MCP_PROVIDER_MAX_TOKENS", "2000")),
                is_default=True,
            )
            # Replace existing providers with the env-defined one
            config.providers = [provider]
        except ValueError as e:
            print(f"[vision_mcp] WARNING: Invalid VISION_MCP_PROVIDER_* config: {e}", file=sys.stderr)


def get_config() -> SimpleConfig:
    """Return cached SimpleConfig singleton."""
    global _simple_config
    if _simple_config is None:
        _simple_config = _load_simple_config()
    return _simple_config


def reload_config() -> SimpleConfig:
    """Clear and reload SimpleConfig."""
    global _simple_config
    _simple_config = None
    return get_config()
