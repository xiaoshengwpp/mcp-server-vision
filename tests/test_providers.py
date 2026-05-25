"""Tests for provider implementations."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from vision_mcp.providers.base import (
    AnalysisResult,
    BaseProvider,
    OpenAICompatibleProvider,
    OllamaProvider,
    AnthropicProvider,
    ProviderRegistry,
)


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider
# ---------------------------------------------------------------------------


class TestOpenAICompatibleProvider:
    """Test OpenAI-compatible provider (DashScope, OpenAI, etc.)."""

    @pytest.mark.asyncio
    async def test_analyze_image(self):
        """Successful image analysis returns AnalysisResult."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "A red circle on white background"
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        result = await provider.analyze("base64data", "Describe this image")

        assert isinstance(result, AnalysisResult)
        assert result.text == "A red circle on white background"
        assert result.model == "test-model"
        assert result.provider == "openai_compatible"
        assert result.usage is not None

    @pytest.mark.asyncio
    async def test_custom_name(self):
        """Provider can have a custom name."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="qwen-vl-max",
            name="dashscope",
        )
        assert provider.name == "dashscope"

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Provider retries on transient failures."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_retries=2,
        )

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            Exception("Connection error"),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": "Success on retry"}}],
                    "usage": {},
                }),
                raise_for_status=MagicMock(),
            ),
        ]
        provider._client = mock_client

        with patch('vision_mcp.providers.base.asyncio.sleep', new_callable=AsyncMock):
            result = await provider.analyze("data", "prompt")
            assert result.text == "Success on retry"

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        """RuntimeError raised when all retries are exhausted."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_retries=2,
        )

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Always fails")
        provider._client = mock_client

        with patch('vision_mcp.providers.base.asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="All 2 attempts failed"):
                await provider.analyze("data", "prompt")

    @pytest.mark.asyncio
    async def test_close(self):
        """close() properly shuts down the HTTP client."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        mock_client = AsyncMock()
        provider._client = mock_client

        await provider.close()
        mock_client.aclose.assert_called_once()
        assert provider._client is None


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    """Test Ollama local provider."""

    @pytest.mark.asyncio
    async def test_analyze_image(self):
        provider = OllamaProvider(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "I see a cat"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        result = await provider.analyze("base64data", "Describe this")

        assert isinstance(result, AnalysisResult)
        assert result.text == "I see a cat"
        assert result.provider == "ollama"

    @pytest.mark.asyncio
    async def test_custom_model(self):
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="llava:13b",
        )
        assert provider.model == "llava:13b"


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    """Test Anthropic Claude provider."""

    @pytest.mark.asyncio
    async def test_analyze_image(self):
        provider = AnthropicProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "A beautiful landscape"}],
            "usage": {"input_tokens": 200, "output_tokens": 30},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        result = await provider.analyze("base64data", "Describe this")

        assert isinstance(result, AnalysisResult)
        assert result.text == "A beautiful landscape"
        assert result.provider == "anthropic"
        assert result.usage["input_tokens"] == 200

    @pytest.mark.asyncio
    async def test_analyze_multiple_images(self):
        """Anthropic provider sends all images in a single request."""
        provider = AnthropicProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Both images show cats"}],
            "usage": {"input_tokens": 400, "output_tokens": 50},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        result = await provider.analyze_multiple(
            ["img1_base64", "img2_base64"],
            "Compare these",
        )

        assert isinstance(result, AnalysisResult)
        assert result.text == "Both images show cats"
        assert result.usage["input_tokens"] == 400

        # Verify the request payload contains 2 image blocks + 1 text block
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        content = payload["messages"][0]["content"]
        image_blocks = [b for b in content if b["type"] == "image"]
        text_blocks = [b for b in content if b["type"] == "text"]
        assert len(image_blocks) == 2
        assert len(text_blocks) == 1


# ---------------------------------------------------------------------------
# OpenAI analyze_multiple
# ---------------------------------------------------------------------------


class TestOpenAIMultiImage:
    """Test OpenAI-compatible provider multi-image support."""

    @pytest.mark.asyncio
    async def test_analyze_multiple_images(self):
        """OpenAI provider sends all images in a single request."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4o",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Image 1 shows a dog, Image 2 shows a cat"
                }
            }],
            "usage": {"prompt_tokens": 300, "completion_tokens": 40},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._client = mock_client

        result = await provider.analyze_multiple(
            ["img1_b64", "img2_b64", "img3_b64"],
            "Compare all three",
        )

        assert isinstance(result, AnalysisResult)
        assert "dog" in result.text
        assert result.provider == "openai_compatible"

        # Verify the request has 3 image_url blocks + 1 text block
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        content = payload["messages"][0]["content"]
        image_blocks = [b for b in content if b["type"] == "image_url"]
        text_blocks = [b for b in content if b["type"] == "text"]
        assert len(image_blocks) == 3
        assert len(text_blocks) == 1

    @pytest.mark.asyncio
    async def test_analyze_multiple_retry_on_failure(self):
        """Multi-image request retries on transient failure."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="gpt-4o",
            max_retries=2,
        )

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            Exception("timeout"),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": "Success"}}],
                    "usage": {},
                }),
                raise_for_status=MagicMock(),
            ),
        ]
        provider._client = mock_client

        with patch('vision_mcp.providers.base.asyncio.sleep', new_callable=AsyncMock):
            result = await provider.analyze_multiple(["d1", "d2"], "prompt")
            assert result.text == "Success"


# ---------------------------------------------------------------------------
# Ollama analyze_multiple fallback
# ---------------------------------------------------------------------------


class TestOllamaMultiImage:
    """Test Ollama multi-image fallback (sequential)."""

    @pytest.mark.asyncio
    async def test_fallback_to_sequential(self):
        """Ollama falls back to sequential analysis via base class."""
        provider = OllamaProvider(base_url="http://localhost:11434")

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={"response": "First image"}),
                raise_for_status=MagicMock(),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={"response": "Second image"}),
                raise_for_status=MagicMock(),
            ),
        ]
        provider._client = mock_client

        result = await provider.analyze_multiple(["d1", "d2"], "Compare")

        # Should have made 2 separate API calls (sequential fallback)
        assert mock_client.post.call_count == 2
        assert "First image" in result.text
        assert "Second image" in result.text


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """Test provider registry management."""

    def test_register_and_get(self):
        registry = ProviderRegistry()
        provider = OllamaProvider(name="test-ollama")
        registry.register(provider, default=True)

        assert registry.get("test-ollama") is provider
        assert registry.get() is provider  # default

    def test_default_provider(self):
        registry = ProviderRegistry()
        p1 = OllamaProvider(name="p1")
        p2 = OllamaProvider(name="p2")

        registry.register(p1)
        assert registry.default == "p1"

        registry.register(p2, default=True)
        assert registry.default == "p2"

    def test_list_providers(self):
        registry = ProviderRegistry()
        registry.register(OllamaProvider(name="a"))
        registry.register(OllamaProvider(name="b"))

        assert sorted(registry.list_providers()) == ["a", "b"]

    def test_get_nonexistent_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="not found"):
            registry.get("nonexistent")

    def test_no_default_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="No default"):
            registry.get()
