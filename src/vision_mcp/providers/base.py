"""Provider abstraction layer for multi-backend support."""
from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Standardized analysis result."""
    text: str
    model: str
    provider: str
    usage: dict[str, int] | None = None
    raw_response: dict[str, Any] | None = None


class BaseProvider(abc.ABC):
    """Abstract base class for vision providers."""

    _client: httpx.AsyncClient | None = None
    model: str
    timeout: float

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...

    @abc.abstractmethod
    async def analyze(
        self,
        image_data: str,
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Analyze an image and return structured result."""
        ...

    async def analyze_multiple(
        self,
        image_data_list: list[str],
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Analyze multiple images in a single request.

        Providers that natively support multi-image requests (OpenAI,
        Anthropic) override this to send all images at once.  The default
        implementation falls back to sequential per-image analysis and
        concatenates the results.
        """
        texts: list[str] = []
        for i, data in enumerate(image_data_list, 1):
            single_prompt = f"Image {i} of {len(image_data_list)}: {prompt}"
            result = await self.analyze(data, single_prompt, detail, model_override)
            texts.append(f"## Image {i}\n{result.text}")
        combined = "\n\n".join(texts)
        return AnalysisResult(
            text=combined,
            model=self.model,
            provider=self.name,
        )

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create a long-lived async client for connection reuse."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI-compatible API provider (OpenAI, DashScope, etc.)

    Supports any API that follows the OpenAI chat completions format
    with image_url content blocks.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        name: str = "openai_compatible",
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._name = name
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return self._name

    async def analyze(
        self,
        image_data: str,
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Analyze image via OpenAI-compatible chat completions API."""

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build message with image
        payload = {
            "model": model_override or self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                                "detail": detail,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            "max_tokens": 2000,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()

                # Extract response
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                logger.info(f"{self.name}: Analysis complete (attempt {attempt + 1})")

                return AnalysisResult(
                    text=text,
                    model=model_override or self.model,
                    provider=self.name,
                    usage=usage,
                    raw_response=data,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"{self.name}: Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        raise RuntimeError(f"{self.name}: All {self.max_retries} attempts failed. Last error: {last_error}")

    async def analyze_multiple(
        self,
        image_data_list: list[str],
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Send multiple images in a single OpenAI-compatible request."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build content blocks: one image_url per image + text prompt
        content: list[dict[str, Any]] = []
        for i, data in enumerate(image_data_list, 1):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{data}",
                    "detail": detail,
                },
            })
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": model_override or self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 2000,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                logger.info(
                    f"{self.name}: Multi-image analysis complete "
                    f"({len(image_data_list)} images, attempt {attempt + 1})"
                )

                return AnalysisResult(
                    text=text,
                    model=model_override or self.model,
                    provider=self.name,
                    usage=usage,
                    raw_response=data,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"{self.name}: Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"{self.name}: All {self.max_retries} attempts failed. "
            f"Last error: {last_error}"
        )


class OllamaProvider(BaseProvider):
    """Ollama local vision model provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llava:latest",
        name: str = "ollama",
        timeout: float = 120.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._name = name
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return self._name

    async def analyze(
        self,
        image_data: str,
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Analyze image via Ollama API."""

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model_override or self.model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post(url, json=payload)
                response.raise_for_status()

                data = response.json()
                text = data.get("response", "")

                logger.info(f"{self.name}: Analysis complete (attempt {attempt + 1})")

                return AnalysisResult(
                    text=text,
                    model=model_override or self.model,
                    provider=self.name,
                    usage=None,
                    raw_response=data,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"{self.name}: Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"{self.name}: All {self.max_retries} attempts failed. Last error: {last_error}")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude vision API provider.

    Supports the official Anthropic API as well as third-party
    Anthropic-compatible endpoints (proxies, AWS Bedrock, etc.)
    by accepting an optional ``base_url``.
    """

    _DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        name: str = "anthropic",
        base_url: str = "",
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self._name = name
        self.base_url = (base_url.strip().rstrip("/") if base_url else self._DEFAULT_BASE_URL)
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return self._name

    async def analyze(
        self,
        image_data: str,
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Analyze image via Anthropic Messages API."""

        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_override or self.model,
            "max_tokens": 2000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()

                # Extract response
                text = data["content"][0]["text"]
                usage = {
                    "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                }

                logger.info(f"{self.name}: Analysis complete (attempt {attempt + 1})")

                return AnalysisResult(
                    text=text,
                    model=model_override or self.model,
                    provider=self.name,
                    usage=usage,
                    raw_response=data,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"{self.name}: Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"{self.name}: All {self.max_retries} attempts failed. Last error: {last_error}")

    async def analyze_multiple(
        self,
        image_data_list: list[str],
        prompt: str,
        detail: str = "auto",
        model_override: str | None = None,
    ) -> AnalysisResult:
        """Send multiple images in a single Anthropic Messages API request."""
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Build content blocks: one image per image + text prompt
        content: list[dict[str, Any]] = []
        for data in image_data_list:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": data,
                },
            })
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": model_override or self.model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": content}],
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()
                text = data["content"][0]["text"]
                usage = {
                    "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                }

                logger.info(
                    f"{self.name}: Multi-image analysis complete "
                    f"({len(image_data_list)} images, attempt {attempt + 1})"
                )

                return AnalysisResult(
                    text=text,
                    model=model_override or self.model,
                    provider=self.name,
                    usage=usage,
                    raw_response=data,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"{self.name}: Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"{self.name}: All {self.max_retries} attempts failed. "
            f"Last error: {last_error}"
        )


class ProviderRegistry:
    """Registry for managing multiple vision providers."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._default: str | None = None

    def register(self, provider: BaseProvider, default: bool = False) -> None:
        """Register a provider."""
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name
        logger.info(f"Registered provider: {provider.name} (default={default})")

    def get(self, name: str | None = None) -> BaseProvider:
        """Get a provider by name, or default if not specified."""
        if name is None:
            if self._default is None:
                raise ValueError("No default provider registered")
            name = self._default

        if name not in self._providers:
            available = ", ".join(self._providers.keys())
            raise ValueError(f"Provider '{name}' not found. Available: {available}")

        return self._providers[name]

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    @property
    def default(self) -> str | None:
        """Get default provider name."""
        return self._default


# Global registry instance
registry = ProviderRegistry()
