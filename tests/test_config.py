"""Tests for configuration module."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from vision_mcp.config import (
    ProviderConfig,
    SimpleConfig,
    _resolve_env_vars,
    _load_simple_config,
    get_config,
    reload_config,
)


# ---------------------------------------------------------------------------
# ProviderConfig validation
# ---------------------------------------------------------------------------


class TestProviderConfig:
    """Test provider configuration validation."""

    def test_valid_openai_provider(self):
        p = ProviderConfig(
            name="my-openai",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-xxx",
            model="gpt-4o",
        )
        assert p.name == "my-openai"
        assert p.type == "openai"
        assert p.base_url == "https://api.openai.com/v1"
        assert p.model == "gpt-4o"

    def test_valid_anthropic_provider_no_base_url(self):
        """Anthropic type doesn't require base_url."""
        p = ProviderConfig(
            name="claude",
            type="anthropic",
            api_key="sk-ant-xxx",
            model="claude-3-5-sonnet-20241022",
        )
        assert p.type == "anthropic"
        assert p.base_url == ""

    def test_valid_anthropic_with_base_url_ignored(self):
        """Anthropic accepts base_url but it's ignored at runtime."""
        p = ProviderConfig(
            name="claude",
            type="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-xxx",
            model="claude-3-5-sonnet-20241022",
        )
        assert p.base_url == "https://api.anthropic.com/v1"

    def test_valid_ollama_provider_no_api_key(self):
        """Ollama type doesn't require api_key."""
        p = ProviderConfig(
            name="local",
            type="ollama",
            base_url="http://localhost:11434",
            model="llava",
        )
        assert p.type == "ollama"
        assert p.api_key == ""

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError, match="Provider type must be"):
            ProviderConfig(
                name="bad",
                type="unknown",
                base_url="http://x",
                api_key="k",
                model="m",
            )

    def test_openai_without_base_url_rejected(self):
        with pytest.raises(ValueError, match="base_url"):
            ProviderConfig(
                name="no-url",
                type="openai",
                base_url="",
                api_key="sk-xxx",
                model="gpt-4o",
            )

    def test_ollama_without_base_url_rejected(self):
        with pytest.raises(ValueError, match="base_url"):
            ProviderConfig(
                name="no-url",
                type="ollama",
                base_url="",
                model="llava",
            )

    def test_openai_without_api_key_accepted(self):
        """Local OpenAI-compatible services (vLLM, LM Studio) may not require api_key."""
        p = ProviderConfig(
            name="local-vllm",
            type="openai",
            base_url="http://localhost:8000/v1",
            api_key="",
            model="local-model",
        )
        assert p.api_key == ""

    def test_anthropic_without_api_key_accepted(self):
        """api_key is not enforced at config level — runtime will reject if needed."""
        p = ProviderConfig(
            name="no-key",
            type="anthropic",
            api_key="",
            model="claude-3",
        )
        assert p.api_key == ""

    def test_ollama_without_api_key_accepted(self):
        """Ollama doesn't need api_key."""
        p = ProviderConfig(
            name="local",
            type="ollama",
            base_url="http://localhost:11434",
            api_key="",
            model="llava",
        )
        assert p.api_key == ""

    def test_without_model_rejected(self):
        with pytest.raises(ValueError, match="model"):
            ProviderConfig(
                name="no-model",
                type="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-xxx",
                model="",
            )

    def test_whitespace_stripped(self):
        p = ProviderConfig(
            name="  spaces  ",
            type="  OPENAI  ",
            base_url="  https://api.openai.com/v1/  ",
            api_key="  sk-xxx  ",
            model="  gpt-4o  ",
        )
        assert p.name == "spaces"
        assert p.type == "openai"
        assert p.base_url == "https://api.openai.com/v1"
        assert p.api_key == "sk-xxx"
        assert p.model == "gpt-4o"

    def test_is_default_flag(self):
        p = ProviderConfig(
            name="default",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-xxx",
            model="gpt-4o",
            is_default=True,
        )
        assert p.is_default is True

    def test_is_default_false_by_default(self):
        p = ProviderConfig(
            name="p",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-xxx",
            model="gpt-4o",
        )
        assert p.is_default is False


# ---------------------------------------------------------------------------
# _resolve_env_vars
# ---------------------------------------------------------------------------


class TestResolveEnvVars:
    """Test environment variable substitution."""

    def test_simple_substitution(self):
        with patch.dict(os.environ, {"MY_KEY": "hello"}):
            assert _resolve_env_vars("${MY_KEY}") == "hello"

    def test_missing_var_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _resolve_env_vars("${NONEXISTENT_VAR_12345}") == ""

    def test_no_substitution_needed(self):
        assert _resolve_env_vars("plain string") == "plain string"

    def test_multiple_vars_in_one_string(self):
        with patch.dict(os.environ, {"HOST": "api.example.com", "PATH": "/v1"}):
            result = _resolve_env_vars("https://${HOST}${PATH}")
            assert result == "https://api.example.com/v1"

    def test_partial_substitution(self):
        with patch.dict(os.environ, {"KEY": "value"}):
            result = _resolve_env_vars("prefix-${KEY}-suffix")
            assert result == "prefix-value-suffix"

    def test_list_substitution(self):
        with patch.dict(os.environ, {"A": "x", "B": "y"}):
            result = _resolve_env_vars(["${A}", "${B}", "plain"])
            assert result == ["x", "y", "plain"]

    def test_dict_substitution(self):
        with patch.dict(os.environ, {"KEY": "secret"}):
            result = _resolve_env_vars({"api_key": "${KEY}", "name": "test"})
            assert result == {"api_key": "secret", "name": "test"}

    def test_nested_dict_list(self):
        with patch.dict(os.environ, {"KEY": "val"}):
            data = {"providers": [{"api_key": "${KEY}"}]}
            result = _resolve_env_vars(data)
            assert result == {"providers": [{"api_key": "val"}]}

    def test_non_string_passthrough(self):
        assert _resolve_env_vars(42) == 42
        assert _resolve_env_vars(3.14) == 3.14
        assert _resolve_env_vars(True) is True
        assert _resolve_env_vars(None) is None


# ---------------------------------------------------------------------------
# SimpleConfig helpers
# ---------------------------------------------------------------------------


class TestSimpleConfig:
    """Test SimpleConfig helper methods."""

    def test_default_allowed_paths(self):
        config = SimpleConfig()
        home = str(Path(os.path.expanduser("~")).resolve())
        tmp = str(Path("/tmp").resolve())
        assert home in config.allowed_paths
        assert tmp in config.allowed_paths

    def test_get_default_provider_empty(self):
        config = SimpleConfig()
        assert config.get_default_provider() is None

    def test_get_default_provider_explicit(self):
        p1 = ProviderConfig(name="a", type="openai", base_url="http://a", api_key="k", model="m")
        p2 = ProviderConfig(name="b", type="openai", base_url="http://b", api_key="k", model="m", is_default=True)
        config = SimpleConfig(providers=[p1, p2])
        assert config.get_default_provider().name == "b"

    def test_get_default_provider_first_when_no_explicit(self):
        p1 = ProviderConfig(name="a", type="openai", base_url="http://a", api_key="k", model="m")
        p2 = ProviderConfig(name="b", type="openai", base_url="http://b", api_key="k", model="m")
        config = SimpleConfig(providers=[p1, p2])
        assert config.get_default_provider().name == "a"

    def test_get_provider_by_name(self):
        p1 = ProviderConfig(name="alpha", type="openai", base_url="http://a", api_key="k", model="m")
        config = SimpleConfig(providers=[p1])
        assert config.get_provider_by_name("alpha") is p1
        assert config.get_provider_by_name("nonexistent") is None


# ---------------------------------------------------------------------------
# YAML loading with env var substitution
# ---------------------------------------------------------------------------


class TestYamlLoading:
    """Test YAML config loading with ${VAR} substitution."""

    def test_load_yaml_with_env_substitution(self, tmp_path):
        """${VAR} in YAML is resolved from environment variables."""
        yaml_content = """
providers:
  - name: test
    type: openai
    base_url: https://api.example.com/v1
    api_key: ${TEST_API_KEY_12345}
    model: gpt-4o
    is_default: true
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        with patch.dict(os.environ, {"TEST_API_KEY_12345": "sk-test-key"}):
            config = _load_simple_config(yaml_file)

        assert len(config.providers) == 1
        assert config.providers[0].api_key == "sk-test-key"
        assert config.providers[0].model == "gpt-4o"

    def test_load_yaml_missing_env_var_becomes_empty(self, tmp_path):
        """${MISSING_VAR} resolves to empty string, but provider is still loaded (api_key not enforced)."""
        yaml_content = """
providers:
  - name: test
    type: openai
    base_url: https://api.example.com/v1
    api_key: ${TOTALLY_MISSING_VAR_99999}
    model: gpt-4o
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        with patch.dict(os.environ, {}, clear=True):
            config = _load_simple_config(yaml_file)

        # Provider is loaded even with empty api_key (local services may not need auth)
        assert len(config.providers) == 1
        assert config.providers[0].api_key == ""

    def test_load_yaml_multiple_providers(self, tmp_path):
        yaml_content = """
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DS_KEY}
    model: qwen-vl-max
    is_default: true
  - name: openai
    type: openai
    base_url: https://api.openai.com/v1
    api_key: ${OA_KEY}
    model: gpt-4o
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        with patch.dict(os.environ, {"DS_KEY": "sk-ds", "OA_KEY": "sk-oa"}):
            config = _load_simple_config(yaml_file)

        assert len(config.providers) == 2
        assert config.providers[0].api_key == "sk-ds"
        assert config.providers[1].api_key == "sk-oa"

    def test_dotenv_loaded_before_yaml(self, tmp_path):
        """Values from .env are available when resolving YAML ${VAR}."""
        dotenv = tmp_path / ".env"
        dotenv.write_text("MY_SECRET_KEY=from-dotenv\n")

        yaml_content = """
providers:
  - name: test
    type: openai
    base_url: https://api.example.com/v1
    api_key: ${MY_SECRET_KEY}
    model: gpt-4o
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        with patch('vision_mcp.config.Path.cwd', return_value=tmp_path):
            config = _load_simple_config(yaml_file)

        assert len(config.providers) == 1
        assert config.providers[0].api_key == "from-dotenv"

        # Cleanup env var set by dotenv loading
        os.environ.pop("MY_SECRET_KEY", None)


# ---------------------------------------------------------------------------
# Environment variable single-provider mode
# ---------------------------------------------------------------------------


class TestEnvProviderMode:
    """Test VISION_MCP_PROVIDER_* environment variable configuration."""

    @patch('vision_mcp.config._find_simple_config_yaml', return_value=None)
    def test_env_creates_single_provider(self, mock_find):
        env = {
            "VISION_MCP_PROVIDER_TYPE": "openai",
            "VISION_MCP_PROVIDER_BASE_URL": "https://api.example.com/v1",
            "VISION_MCP_PROVIDER_API_KEY": "sk-env",
            "VISION_MCP_PROVIDER_MODEL": "gpt-4o-mini",
            "VISION_MCP_PROVIDER_NAME": "env-provider",
        }
        with patch.dict(os.environ, env, clear=False):
            config = _load_simple_config()

        assert len(config.providers) == 1
        assert config.providers[0].name == "env-provider"
        assert config.providers[0].type == "openai"
        assert config.providers[0].model == "gpt-4o-mini"
        assert config.providers[0].is_default is True

    def test_env_overrides_yaml_providers(self, tmp_path):
        """VISION_MCP_PROVIDER_* replaces providers from YAML."""
        yaml_content = """
providers:
  - name: yaml-provider
    type: openai
    base_url: https://yaml.example.com/v1
    api_key: sk-yaml
    model: gpt-4o
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        env = {
            "VISION_MCP_PROVIDER_TYPE": "openai",
            "VISION_MCP_PROVIDER_BASE_URL": "https://env.example.com/v1",
            "VISION_MCP_PROVIDER_API_KEY": "sk-env",
            "VISION_MCP_PROVIDER_MODEL": "gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=False):
            config = _load_simple_config(yaml_file)

        assert len(config.providers) == 1
        assert config.providers[0].model == "gpt-4o-mini"

    @patch('vision_mcp.config._find_simple_config_yaml', return_value=None)
    def test_env_invalid_provider_warns_and_skips(self, mock_find):
        """Invalid VISION_MCP_PROVIDER_* config doesn't crash."""
        env = {
            "VISION_MCP_PROVIDER_TYPE": "openai",
            "VISION_MCP_PROVIDER_BASE_URL": "",
            "VISION_MCP_PROVIDER_API_KEY": "",
            "VISION_MCP_PROVIDER_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            config = _load_simple_config()

        assert len(config.providers) == 0
