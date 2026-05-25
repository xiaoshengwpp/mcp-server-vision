"""Vision MCP Server - Main entry point."""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .config import get_config
from .media import ImagePayload, VideoPayload, load_image, load_video
from .providers import registry, OpenAICompatibleProvider, OllamaProvider, AnthropicProvider
from .security import SecurityConfig as _SecurityConfig, validate_file, validate_local_path, check_file_size, validate_url

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP(
    name="vision-mcp",
    instructions="Production-grade Vision MCP Server - Multi-provider image/video analysis with security-first design",
)


def _get_security_config() -> _SecurityConfig:
    """Build a SecurityConfig from the current SimpleConfig settings."""
    config = get_config()
    return _SecurityConfig(
        allowed_paths=config.allowed_paths,
        max_file_size=int(max(config.max_image_size_mb, config.max_video_size_mb) * 1024 * 1024),
        max_image_pixels=config.max_image_pixels,
    )


def initialize_providers() -> None:
    """Initialize providers from config."""
    config = get_config()

    for p_config in config.providers:
        try:
            if p_config.type == "openai":
                provider = OpenAICompatibleProvider(
                    name=p_config.name,
                    base_url=p_config.base_url,
                    api_key=p_config.api_key,
                    model=p_config.model,
                    timeout=config.api_timeout,
                    max_retries=config.max_retries,
                )
                registry.register(provider, default=p_config.is_default)
                logger.info(f"Registered OpenAI-compatible provider: {p_config.name} ({p_config.model})")

            elif p_config.type == "anthropic":
                provider = AnthropicProvider(
                    name=p_config.name,
                    api_key=p_config.api_key,
                    model=p_config.model,
                    timeout=config.api_timeout,
                    max_retries=config.max_retries,
                )
                registry.register(provider, default=p_config.is_default)
                logger.info(f"Registered Anthropic provider: {p_config.name} ({p_config.model})")

            elif p_config.type == "ollama":
                provider = OllamaProvider(
                    name=p_config.name,
                    base_url=p_config.base_url,
                    model=p_config.model,
                    timeout=config.api_timeout,
                    max_retries=config.max_retries,
                )
                registry.register(provider, default=p_config.is_default)
                logger.info(f"Registered Ollama provider: {p_config.name} ({p_config.model})")

        except Exception as e:
            logger.error(f"Failed to register provider '{p_config.name}': {e}")

    if not registry.list_providers():
        logger.warning("No providers configured! Add providers to config.yaml or set VISION_MCP_PROVIDER_* env vars")


@mcp.tool()
async def analyze_image(
    source: Annotated[str, Field(description="Image source: local path or URL")],
    prompt: Annotated[str, Field(description="Analysis prompt", default="Describe this image in detail")] = "Describe this image in detail",
    detail: Annotated[str, Field(description="Detail level: low, auto, high", default="auto")] = "auto",
    provider: Annotated[str | None, Field(description="Provider name (optional)", default=None)] = None,
    model: Annotated[str | None, Field(description="Model name override (optional, e.g. qwen-vl-plus, gpt-4o-mini)", default=None)] = None,
) -> str:
    """
    Analyze a single image using vision AI.
    
    Supports local files and URLs. Performs security validation before processing.
    """
    try:
        sec_config = _get_security_config()

        # Validate source
        if source.startswith(("http://", "https://")):
            validate_url(source, config=sec_config)
        else:
            validate_file(Path(source), config=sec_config)

        # Load image
        logger.info(f"Loading image: {source}")
        image_payload = await load_image(source, config=sec_config)

        # Get provider
        prov = registry.get(provider)

        # Analyze
        logger.info(f"Analyzing with {prov.name} (model={model or prov.model})...")
        result = await prov.analyze(image_payload.data, prompt, detail=detail, model_override=model)

        return result.text

    except Exception as e:
        logger.error(f"analyze_image failed: {e}", exc_info=True)
        return f"❌ Error: {e}"


@mcp.tool()
async def analyze_multiple_images(
    sources: Annotated[list[str], Field(description="List of image sources (local paths or URLs)", min_length=2, max_length=10)],
    prompt: Annotated[str, Field(description="Comparison prompt", default="Compare these images and describe their differences")] = "Compare these images and describe their differences",
    provider: Annotated[str | None, Field(description="Provider name (optional)", default=None)] = None,
    model: Annotated[str | None, Field(description="Model name override (optional)", default=None)] = None,
) -> str:
    """
    Compare multiple images using vision AI.
    
    Supports 2-10 images. Useful for finding differences, tracking changes, etc.
    """
    try:
        if len(sources) < 2:
            return "❌ Error: At least 2 images required for comparison"
        if len(sources) > 10:
            return "❌ Error: Maximum 10 images supported"

        sec_config = _get_security_config()

        # Validate and load all images
        images_data = []
        for i, source in enumerate(sources, 1):
            if source.startswith(("http://", "https://")):
                validate_url(source, config=sec_config)
            else:
                validate_file(Path(source), config=sec_config)

            logger.info(f"Loading image {i}/{len(sources)}: {source}")
            image_payload = await load_image(source, config=sec_config)
            images_data.append(image_payload)

        # Get provider
        prov = registry.get(provider)

        # Use native multi-image support when available
        logger.info(f"Analyzing {len(images_data)} images with {prov.name} (model={model or prov.model})...")
        base64_list = [img.data for img in images_data]
        result = await prov.analyze_multiple(base64_list, prompt, model_override=model)

        return result.text

    except Exception as e:
        logger.error(f"analyze_multiple_images failed: {e}", exc_info=True)
        return f"❌ Error: {e}"


@mcp.tool()
async def analyze_video(
    source: Annotated[str, Field(description="Video source: local path or URL")],
    prompt: Annotated[str, Field(description="Analysis prompt", default="Describe this video in detail")] = "Describe this video in detail",
    max_frames: Annotated[int, Field(description="Maximum frames to analyze", default=10, ge=1, le=50)] = 10,
    provider: Annotated[str | None, Field(description="Provider name (optional)", default=None)] = None,
    model: Annotated[str | None, Field(description="Model name override (optional)", default=None)] = None,
) -> str:
    """
    Analyze a video using vision AI.
    
    Extracts frames and analyzes them to understand video content.
    Supports local files and URLs.
    """
    try:
        sec_config = _get_security_config()

        # Validate source (videos use path+size validation, not image MIME checks)
        if source.startswith(("http://", "https://")):
            validate_url(source, config=sec_config)
        else:
            validate_local_path(source, config=sec_config)
            check_file_size(source, config=sec_config)

        # Load video frames
        logger.info(f"Loading video: {source}")
        video = await load_video(source, num_frames=max_frames, config=sec_config)

        if not video.frames:
            return "❌ Error: No frames extracted from video"

        # Get provider
        prov = registry.get(provider)

        # Analyze frames
        results = []
        for i, frame in enumerate(video.frames, 1):
            logger.info(f"Analyzing frame {i}/{len(video.frames)} (timestamp: {frame.timestamp_sec:.1f}s)...")
            frame_prompt = f"Frame {i}/{len(video.frames)}: {prompt}"
            result = await prov.analyze(frame.data, frame_prompt, model_override=model)
            results.append(f"## Frame {i} (t={frame.timestamp_sec:.1f}s)\n{result.text}")

        return "\n\n".join(results)

    except Exception as e:
        logger.error(f"analyze_video failed: {e}", exc_info=True)
        return f"❌ Error: {e}"


@mcp.tool()
async def ocr_image(
    source: Annotated[str, Field(description="Image source: local path or URL")],
    language: Annotated[str, Field(description="OCR language hint", default="auto")] = "auto",
    provider: Annotated[str | None, Field(description="Provider name (optional)", default=None)] = None,
    model: Annotated[str | None, Field(description="Model name override (optional)", default=None)] = None,
) -> str:
    """
    Extract text from an image using vision AI (OCR).
    
    Optimized prompt for text extraction with language detection.
    """
    try:
        sec_config = _get_security_config()

        # Validate source
        if source.startswith(("http://", "https://")):
            validate_url(source, config=sec_config)
        else:
            validate_file(Path(source), config=sec_config)

        # Load image
        logger.info(f"Loading image for OCR: {source}")
        image_payload = await load_image(source, config=sec_config)

        # Get provider
        prov = registry.get(provider)

        # OCR-specific prompt
        prompt = f"""Extract all visible text from this image.
Language: {language if language != 'auto' else 'auto-detect'}

Requirements:
- Preserve the original layout and structure
- Use markdown formatting for headers, lists, tables
- If text is in columns, separate them clearly
- Include any numbers, symbols, or special characters
- If text is unclear or partially visible, mark with [unclear]

Extract the text now:"""

        # Analyze
        logger.info(f"Performing OCR with {prov.name} (model={model or prov.model})...")
        result = await prov.analyze(image_payload.data, prompt, model_override=model)

        return result.text

    except Exception as e:
        logger.error(f"ocr_image failed: {e}", exc_info=True)
        return f"❌ Error: {e}"


@mcp.tool()
async def get_supported_formats() -> str:
    """
    Get list of supported image/video formats and capabilities.
    """
    config = get_config()
    
    formats = """## Supported Formats

### Images
- **Formats**: JPEG, PNG, GIF, WebP, BMP, SVG
- **Max size**: {max_image_size_mb}MB
- **Max pixels**: {max_image_pixels:,} (≈4000×4000)

### Videos
- **Formats**: MP4, AVI, MOV, MKV, WebM
- **Max size**: {max_video_size_mb}MB (2GB)
- **Max duration**: {max_video_duration} minutes
- **Frame extraction**: Up to 50 frames

### Sources
- **Local files**: Paths within allowed directories
- **URLs**: HTTP/HTTPS (SSRF-protected)

## Available Tools
1. `analyze_image` - Single image analysis
2. `analyze_multiple_images` - Compare 2-10 images
3. `analyze_video` - Video frame analysis
4. `ocr_image` - Text extraction (OCR)
5. `get_supported_formats` - This tool
6. `get_server_status` - Server configuration

## Registered Providers
{providers}
""".format(
        max_image_size_mb=config.max_image_size_mb,
        max_image_pixels=config.max_image_pixels,
        max_video_size_mb=config.max_video_size_mb,
        max_video_duration=config.max_video_duration_minutes,
        providers="\n".join(f"- {name}" for name in registry.list_providers()) or "(none configured)"
    )
    
    return formats


@mcp.tool()
async def get_server_status() -> str:
    """
    Get server configuration and status information.
    """
    config = get_config()
    providers_list = registry.list_providers()
    default_provider = registry.default

    # Build provider detail lines with model names
    provider_details = []
    for name in providers_list:
        prov = registry.get(name)
        model_name = getattr(prov, 'model', 'unknown')
        prov_type = prov.__class__.__name__
        is_default = " *(default)*" if name == default_provider else ""
        provider_details.append(f"- **{name}** ({prov_type}): `{model_name}`{is_default}")
    provider_detail_str = "\n".join(provider_details) if provider_details else "(none configured)"

    status = """## Vision MCP Server Status

### Configuration
- **Version**: 2.0.0
- **Log Level**: {log_level}
- **API Timeout**: {api_timeout}s
- **Max Retries**: {max_retries}

### Providers
{provider_details}

### Security
- **Max Image Size**: {max_image_size_mb}MB
- **Max Video Size**: {max_video_size_mb}MB
- **Max Video Duration**: {max_video_duration} min
- **Max Image Pixels**: {max_image_pixels:,}
- **Allowed Paths**: {allowed_paths}
""".format(
        provider_details=provider_detail_str,
        log_level=config.log_level,
        api_timeout=config.api_timeout,
        max_retries=config.max_retries,
        max_image_size_mb=config.max_image_size_mb,
        max_video_size_mb=config.max_video_size_mb,
        max_video_duration=config.max_video_duration_minutes,
        max_image_pixels=config.max_image_pixels,
        allowed_paths=", ".join(str(p) for p in config.allowed_paths) or "(none)",
    )

    return status


async def serve() -> None:
    """Start the MCP server with configured transport."""
    initialize_providers()
    config = get_config()

    # Apply log level from config
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    logger.info(f"Starting Vision MCP Server (transport={config.transport})...")

    if config.transport == "sse":
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()


async def main() -> None:
    """Alias for serve() — kept for backward compatibility."""
    await serve()


if __name__ == "__main__":
    asyncio.run(main())
