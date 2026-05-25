"""
Vision MCP Server Configuration Module.

Provides centralized configuration management with support for:
- Environment variable overrides (prefix: VISION_MCP_)
- YAML configuration file loading
- Multi-provider configuration (OpenAI-compatible APIs)
- Security restrictions (file size limits, path whitelists, URL blacklists)
- Cache configuration
- Validation via Pydantic v2

Usage:
    from vision_mcp.config import get_settings
    settings = get_settings()

    # Access nested config
    settings.vision_providers.default.base_url
    settings.security.max_file_size_mb
    settings.cache.enabled
"""

from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from pydantic import (
    AnyHttpUrl,
    Field,
    FilePath,
    HttpUrl,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_YAML_PATHS = (
    "config.yaml",
    "config.yml",
    "vision_mcp.yaml",
    "vision_mcp.yml",
    "/etc/vision_mcp/config.yaml",
)

_ENV_PREFIX = "VISION_MCP_"
_DEFAULT_ENV_FILE = ".env"


# ---------------------------------------------------------------------------
# Provider Models
# ---------------------------------------------------------------------------

class VisionProviderConfig(BaseSettings):
    """Configuration for a single OpenAI-compatible vision provider."""

    model_config = SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}PROVIDER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- API connection ---
    base_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("https://api.openai.com/v1"),
        description="OpenAI-compatible API base URL.",
    )
    api_key: str = Field(
        default="",
        description="API key for authentication. Leave empty to use the global key.",
    )
    model: str = Field(
        default="gpt-4o",
        description="Model identifier (e.g. gpt-4o, gpt-4o-mini, qwen-vl-max).",
    )

    # --- Timeouts & retries ---
    timeout_seconds: PositiveFloat = Field(
        default=30.0,
        description="HTTP request timeout in seconds.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts on transient failures.",
    )
    retry_delay_seconds: PositiveFloat = Field(
        default=1.0,
        description="Base delay between retries (exponential backoff applied).",
    )

    # --- Rate limiting ---
    requests_per_minute: Optional[PositiveInt] = Field(
        default=None,
        description="Rate limit: max requests per minute. None = no limit.",
    )
    tokens_per_minute: Optional[PositiveInt] = Field(
        default=None,
        description="Rate limit: max tokens per minute. None = no limit.",
    )

    # --- Provider metadata ---
    provider_name: str = Field(
        default="default",
        description="Human-readable provider identifier.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this provider is active.",
    )

    # --- Logging ---
    log_requests: bool = Field(
        default=False,
        description="Enable debug-level logging of request/response payloads.",
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _strip_api_key(cls, v: str | None) -> str:
        return (v or "").strip()


class MultiProviderConfig(BaseSettings):
    """Container for multiple vision provider configurations."""

    model_config = SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}PROVIDERS_",
        env_nested_delimiter="__",
        extra="allow",
    )

    default: VisionProviderConfig = Field(
        default_factory=VisionProviderConfig,
        description="The default / fallback provider configuration.",
    )
    fallback: Optional[VisionProviderConfig] = Field(
        default=None,
        description="Fallback provider used when the default is unavailable.",
    )
    # Additional providers can be loaded dynamically from YAML.
    extra_providers: Dict[str, VisionProviderConfig] = Field(
        default_factory=dict,
        description="Dynamically loaded extra providers keyed by name.",
    )

    @property
    def all_providers(self) -> Dict[str, VisionProviderConfig]:
        """Return merged dict of all providers (default + fallback + extra)."""
        result: Dict[str, VisionProviderConfig] = {"default": self.default}
        if self.fallback is not None:
            result["fallback"] = self.fallback
        result.update(self.extra_providers)
        return result


# ---------------------------------------------------------------------------
# Security Models
# ---------------------------------------------------------------------------

class SecurityConfig(BaseSettings):
    """Security restrictions for file and URL access."""

    model_config = SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}SECURITY_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- File size limits ---
    max_file_size_mb: PositiveFloat = Field(
        default=20.0,
        description="Maximum image file size in megabytes.",
    )
    max_total_payload_mb: PositiveFloat = Field(
        default=50.0,
        description="Maximum total request payload size in MB.",
    )

    # --- Path whitelist ---
    allowed_paths: List[str] = Field(
        default_factory=lambda: ["/tmp", "/tmp/vision_mcp", os.path.expanduser("~/vision_mcp_data")],
        description="List of directory prefixes that image files may be loaded from.",
    )
    deny_symlinks_outside_whitelist: bool = Field(
        default=True,
        description="Reject symlinks that resolve outside allowed_paths.",
    )

    # --- URL blacklist ---
    blocked_url_patterns: List[str] = Field(
        default_factory=lambda: [
            r"localhost",
            r"127\.0\.0\.1",
            r"0\.0\.0\.0",
            r"169\.254\.",
            r"10\.\d+\.\d+\.\d+",
            r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+",
            r"192\.168\.\d+\.\d+",
            r"file://",
            r"metadata\.google",
            r"169\.254\.169\.254",  # AWS / cloud metadata
        ],
        description="Regex patterns for URLs that must not be fetched.",
    )
    allowed_url_schemes: Set[str] = Field(
        default={"http", "https"},
        description="Only these URL schemes are permitted.",
    )

    # --- API key protection ---
    redact_api_keys_in_logs: bool = Field(
        default=True,
        description="Mask API keys in log output.",
    )

    @field_validator("allowed_paths", mode="before")
    @classmethod
    def _normalize_paths(cls, v: Any) -> List[str]:
        """Ensure paths are expanded and absolute."""
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        return [str(Path(p).expanduser().resolve()) for p in v]

    @field_validator("blocked_url_patterns", mode="before")
    @classmethod
    def _validate_regex_patterns(cls, v: Any) -> List[str]:
        """Ensure every pattern compiles as a valid regex."""
        patterns = v or []
        for p in patterns:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern '{p}': {exc}")
        return patterns

    def is_path_allowed(self, file_path: str | Path) -> Tuple[bool, str]:
        """Check whether *file_path* falls under one of the whitelisted prefixes."""
        resolved = Path(file_path).expanduser().resolve()
        for allowed in self.allowed_paths:
            allowed_resolved = Path(allowed).expanduser().resolve()
            try:
                resolved.relative_to(allowed_resolved)
                return True, ""
            except ValueError:
                continue
        return False, f"Path '{resolved}' is not within any allowed directory"

    def is_url_safe(self, url: str) -> Tuple[bool, str]:
        """Check whether *url* passes scheme and blacklist checks."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        if parsed.scheme not in self.allowed_url_schemes:
            return False, f"URL scheme '{parsed.scheme}' is not allowed"

        netloc = parsed.netloc.lower()
        for pattern in self.blocked_url_patterns:
            if re.search(pattern, netloc, re.IGNORECASE):
                return False, f"URL matches blocked pattern '{pattern}'"

        return True, ""


# ---------------------------------------------------------------------------
# Cache Models
# ---------------------------------------------------------------------------

class CacheConfig(BaseSettings):
    """Configuration for response / image caching."""

    model_config = SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}CACHE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    enabled: bool = Field(
        default=True,
        description="Whether caching is active.",
    )
    backend: str = Field(
        default="disk",
        description="Cache backend: 'memory', 'disk', or 'redis'.",
    )
    ttl_seconds: PositiveInt = Field(
        default=3600,
        description="Default time-to-live for cached entries.",
    )
    max_size_mb: PositiveFloat = Field(
        default=500.0,
        description="Maximum cache size on disk / in memory (MB).",
    )
    disk_cache_dir: str = Field(
        default=os.path.expanduser("~/.cache/vision_mcp"),
        description="Directory for disk-based cache storage.",
    )
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (required when backend='redis').",
    )
    cache_analysis_results: bool = Field(
        default=True,
        description="Cache API analysis results keyed by (model, image_hash).",
    )
    cache_images: bool = Field(
        default=False,
        description="Cache downloaded image content to reduce bandwidth.",
    )

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        allowed = {"memory", "disk", "redis"}
        if v not in allowed:
            raise ValueError(f"backend must be one of {allowed}, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Server / MCP Models
# ---------------------------------------------------------------------------

class ServerConfig(BaseSettings):
    """MCP server runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}SERVER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    host: str = Field(
        default="127.0.0.1",
        description="Bind address for the MCP server.",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Listen port.",
    )
    transport: str = Field(
        default="stdio",
        description="Transport mode: 'stdio' or 'sse'.",
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level.",
    )
    workers: PositiveInt = Field(
        default=1,
        description="Number of worker processes (for SSE transport).",
    )
    cors_origins: List[str] = Field(
        default_factory=list,
        description="Allowed CORS origin patterns (only applies to SSE).",
    )

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("transport")
    @classmethod
    def _validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "sse"}
        if v.lower() not in allowed:
            raise ValueError(f"transport must be one of {allowed}")
        return v.lower()


# ---------------------------------------------------------------------------
# Top-level Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """
    Master configuration object for Vision MCP Server.

    Configuration is loaded from (in priority order, highest first):
      1. Environment variables (prefix: VISION_MCP_)
      2. YAML config file (resolved via VISION_MCP_CONFIG or defaults)
      3. .env file (if present)
      4. Class-level defaults
    """

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_nested_delimiter="__",
        env_file=_DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # ---- Core ----
    app_name: str = Field(default="Vision MCP Server", description="Application display name.")
    version: str = Field(default="0.1.0", description="Application version.")
    debug: bool = Field(default=False, description="Enable debug mode (verbose errors).")

    # ---- YAML config path override ----
    config_file: Optional[str] = Field(
        default=None,
        description="Explicit path to YAML config file. Overrides auto-discovery.",
    )

    # ---- Sections ----
    vision_providers: MultiProviderConfig = Field(
        default_factory=MultiProviderConfig,
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
    )
    server: ServerConfig = Field(
        default_factory=ServerConfig,
    )

    # ---- Misc ----
    system_prompt: str = Field(
        default=(
            "You are a vision analysis assistant. "
            "Describe images in detail, focusing on relevant visual elements."
        ),
        description="Default system prompt sent to vision models.",
    )
    max_concurrent_requests: PositiveInt = Field(
        default=5,
        description="Maximum concurrent API requests across all providers.",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Customise loading order: env > yaml > dotenv > defaults."""
        yaml_path = _resolve_yaml_path()
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
        ]
        if yaml_path is not None:
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_path),
            )
        sources.append(dotenv_settings)
        return tuple(sources)

    @model_validator(mode="after")
    def _apply_debug_log_level(self) -> "Settings":
        """When debug=True, force log_level to DEBUG unless explicitly set."""
        if self.debug and self.server.log_level == "INFO":
            self.server.log_level = "DEBUG"
        return self


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_yaml_path() -> Optional[FilePath]:
    """
    Return the resolved YAML config file path.

    Checks, in order:
      1. VISION_MCP_CONFIG environment variable
      2. Each path in _DEFAULT_YAML_PATHS (cwd + absolute)
      3. ~/.config/vision_mcp/config.yaml
    """
    # 1. Explicit override
    env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_file():
            print(
                f"[vision_mcp] WARNING: VISION_MCP_CONFIG points to non-existent file: {p}",
                file=sys.stderr,
            )
            return None
        return p

    # 2. Default search paths
    for candidate in _DEFAULT_YAML_PATHS:
        p = Path(candidate).expanduser()
        if p.is_absolute() and p.is_file():
            return p
        # also check relative to working directory
        rel = Path.cwd() / p
        if rel.is_file():
            return rel

    # 3. XDG config location
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")))
    xdg_file = xdg / "vision_mcp" / "config.yaml"
    if xdg_file.is_file():
        return xdg_file

    return None


def load_yaml_config(path: str | Path) -> Dict[str, Any]:
    """Load and return a YAML file as a plain dict (safe_load)."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"Config file not found: {p}")
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML config must be a mapping, got {type(data).__name__}")
    return data


def dump_yaml_config(settings: Settings, path: str | Path) -> None:
    """Serialize current settings to a YAML file (for reference / backup)."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        yaml.dump(
            settings.model_dump(mode="python"),
            fh,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()


def reload_settings() -> Settings:
    """Clear cache and reload settings (useful during testing)."""
    get_settings.cache_clear()
    return get_settings()


# ---------------------------------------------------------------------------
# SimpleConfig — flat YAML + env-based configuration for server.py
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as _dc_field


@dataclass
class SimpleConfig:
    """
    Simplified configuration loaded from flat YAML and environment variables.

    Designed for use by ``server.py`` — provides the flat attribute access
    (e.g. ``config.dashscope_api_key``) expected by tool implementations.

    Loading priority (highest first):
      1. Environment variables
      2. ``.env`` file
      3. YAML config file
      4. Defaults
    """

    # Provider API Keys
    dashscope_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = ""
    ollama_model: str = "llava:latest"
    anthropic_api_key: str = ""

    # Model Configuration
    dashscope_model: str = "qwen-vl-max"
    openai_model: str = "gpt-4o"
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # API Settings
    api_timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 2.0

    # Security Limits
    max_image_size_mb: float = 20.0
    max_video_size_mb: float = 2048.0
    max_video_duration_minutes: float = 120.0
    max_image_pixels: int = 16_000_000

    # Paths
    allowed_paths: list[str] = _dc_field(default_factory=list)

    # Blocked domains (SSRF)
    blocked_domains: list[str] = _dc_field(default_factory=lambda: [
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


# ---- SimpleConfig singleton ----

_simple_config: Optional[SimpleConfig] = None
_SIMPLE_CONFIG_YAML_PATHS = (
    "config.yaml",
    "config.yml",
    "vision_mcp.yaml",
    "vision_mcp.yml",
)


def _find_simple_config_yaml() -> Optional[Path]:
    env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p
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


def _load_simple_config(yaml_path: Optional[Path] = None) -> SimpleConfig:
    """Load SimpleConfig from YAML → .env → env vars (ascending priority)."""
    config = SimpleConfig()

    # 1. Load from YAML
    if yaml_path is None:
        yaml_path = _find_simple_config_yaml()
    if yaml_path is not None:
        _apply_yaml_to_simple_config(config, yaml_path)

    # 2. Load from .env
    _apply_dotenv_to_simple_config(config)

    # 3. Load from environment variables (highest priority)
    _apply_env_to_simple_config(config)

    config._normalize()
    return config


def _apply_yaml_to_simple_config(config: SimpleConfig, path: Path) -> None:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return

    _str_keys = {
        "dashscope_api_key", "openai_api_key", "ollama_base_url", "ollama_model",
        "anthropic_api_key", "dashscope_model", "openai_model", "anthropic_model",
        "log_level", "transport",
    }
    _float_keys = {
        "api_timeout", "retry_delay", "max_image_size_mb",
        "max_video_size_mb", "max_video_duration_minutes",
    }
    _int_keys = {"max_retries", "max_image_pixels"}

    for key in _str_keys:
        if key in data and data[key] is not None:
            val = str(data[key])
            if not val.startswith("${"):
                setattr(config, key, val)
    for key in _float_keys:
        if key in data and data[key] is not None:
            setattr(config, key, float(data[key]))
    for key in _int_keys:
        if key in data and data[key] is not None:
            setattr(config, key, int(data[key]))
    if "allowed_paths" in data and isinstance(data["allowed_paths"], list):
        config.allowed_paths = [str(p) for p in data["allowed_paths"]]
    if "blocked_domains" in data and isinstance(data["blocked_domains"], list):
        config.blocked_domains = [str(d) for d in data["blocked_domains"]]


def _apply_dotenv_to_simple_config(config: SimpleConfig) -> None:
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
    _env_mapping: list[tuple[str, str, type]] = [
        ("dashscope_api_key", "DASHSCOPE_API_KEY", str),
        ("openai_api_key", "OPENAI_API_KEY", str),
        ("ollama_base_url", "OLLAMA_BASE_URL", str),
        ("ollama_model", "OLLAMA_MODEL", str),
        ("anthropic_api_key", "ANTHROPIC_API_KEY", str),
        ("dashscope_model", "DASHSCOPE_MODEL", str),
        ("openai_model", "OPENAI_MODEL", str),
        ("anthropic_model", "ANTHROPIC_MODEL", str),
        ("api_timeout", "VISION_MCP_API_TIMEOUT", float),
        ("max_retries", "VISION_MCP_MAX_RETRIES", int),
        ("retry_delay", "VISION_MCP_RETRY_DELAY", float),
        ("max_image_size_mb", "MAX_IMAGE_SIZE_MB", float),
        ("max_video_size_mb", "MAX_VIDEO_SIZE_MB", float),
        ("max_video_duration_minutes", "MAX_VIDEO_DURATION_MINUTES", float),
        ("max_image_pixels", "MAX_IMAGE_PIXELS", int),
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
