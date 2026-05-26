"""Tests for MCP server tools."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from vision_mcp.server import (
    analyze_image,
    analyze_multiple_images,
    analyze_video,
    ocr_image,
    get_supported_formats,
    get_server_status,
    initialize_providers,
    registry,
)
from vision_mcp.media import ImagePayload, VideoPayload, VideoFrame
from vision_mcp.security import SecurityConfig as _SecurityConfig
from vision_mcp.providers.base import AnalysisResult, ProviderRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image_payload(data: str = "dGVzdA==") -> ImagePayload:
    return ImagePayload(
        data=data,
        mime_type="image/jpeg",
        width=100,
        height=100,
    )


def _make_analysis_result(text: str = "Test result") -> AnalysisResult:
    return AnalysisResult(text=text, model="test", provider="test")


def _mock_provider(text: str = "Test result"):
    prov = AsyncMock()
    prov.name = "test"
    prov.analyze.return_value = _make_analysis_result(text)
    return prov


def _patch_security(tmp_path):
    """Return a patch that allows all paths through security validation."""
    sec = _SecurityConfig(allowed_paths=[str(tmp_path), "/tmp", "/private"])
    return patch('vision_mcp.server._get_security_config', return_value=sec)


# ---------------------------------------------------------------------------
# analyze_image
# ---------------------------------------------------------------------------


class TestAnalyzeImage:
    """Test analyze_image tool."""

    @pytest.mark.asyncio
    async def test_analyze_local_image(self, tmp_path):
        """Analyzing a local image returns provider text."""
        from PIL import Image

        test_file = tmp_path / "test.jpg"
        Image.new('RGB', (100, 100), color='red').save(test_file, 'JPEG')

        mock_prov = _mock_provider("A red square")
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_prov

        with _patch_security(tmp_path), \
             patch('vision_mcp.server.registry', mock_registry), \
             patch('vision_mcp.server.load_image', new_callable=AsyncMock,
                   return_value=_make_image_payload()) as mock_load:

            result = await analyze_image(
                source=str(test_file),
                prompt="Describe this image",
            )

            assert result == "A red square"
            mock_load.assert_called_once()
            mock_prov.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_url_image(self):
        """Analyzing a URL returns provider text."""
        mock_prov = _mock_provider("URL result")
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_prov

        with patch('vision_mcp.server.registry', mock_registry), \
             patch('vision_mcp.server.load_image', new_callable=AsyncMock,
                   return_value=_make_image_payload()), \
             patch('vision_mcp.server.validate_url', return_value="https://example.com/img.jpg"):

            result = await analyze_image(
                source="https://example.com/image.jpg",
                prompt="What is this?",
            )

            assert result == "URL result"

    @pytest.mark.asyncio
    async def test_error_returns_error_string(self, tmp_path):
        """Errors are caught and returned as error strings."""
        with patch('vision_mcp.server.validate_file', side_effect=Exception("test error")):
            result = await analyze_image(
                source=str(tmp_path / "missing.jpg"),
                prompt="test",
            )
            assert "❌" in result
            assert "test error" in result


# ---------------------------------------------------------------------------
# analyze_multiple_images
# ---------------------------------------------------------------------------


class TestAnalyzeMultipleImages:
    """Test analyze_multiple_images tool."""

    @pytest.mark.asyncio
    async def test_analyze_two_images(self, tmp_path):
        """Comparing two images returns combined results."""
        from PIL import Image

        f1 = tmp_path / "test1.jpg"
        f2 = tmp_path / "test2.jpg"
        Image.new('RGB', (100, 100), color='red').save(f1, 'JPEG')
        Image.new('RGB', (100, 100), color='blue').save(f2, 'JPEG')

        mock_prov = AsyncMock()
        mock_prov.name = "test"
        mock_prov.analyze_multiple.return_value = _make_analysis_result(
            "Image 1 shows red, Image 2 shows blue"
        )
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_prov

        with _patch_security(tmp_path), \
             patch('vision_mcp.server.registry', mock_registry), \
             patch('vision_mcp.server.load_image', new_callable=AsyncMock,
                   return_value=_make_image_payload()):

            result = await analyze_multiple_images(
                sources=[str(f1), str(f2)],
                prompt="Compare these",
            )

            assert "red" in result
            assert "blue" in result
            # Verify analyze_multiple was called (not analyze in a loop)
            mock_prov.analyze_multiple.assert_called_once()

    @pytest.mark.asyncio
    async def test_too_few_images(self):
        """Single source returns error."""
        result = await analyze_multiple_images(
            sources=["https://example.com/img.jpg"],
            prompt="Compare",
        )
        assert "Error" in result


# ---------------------------------------------------------------------------
# analyze_video
# ---------------------------------------------------------------------------


class TestAnalyzeVideo:
    """Test analyze_video tool."""

    @pytest.mark.asyncio
    async def test_analyze_video(self, tmp_path):
        """Analyzing a video returns per-frame results."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video")

        video_payload = VideoPayload(
            frames=[
                VideoFrame(data="dGVzdDE=", timestamp_sec=0.0, frame_index=0),
                VideoFrame(data="dGVzdDI=", timestamp_sec=1.0, frame_index=1),
            ],
        )

        mock_prov = AsyncMock()
        mock_prov.name = "test"
        mock_prov.analyze.side_effect = [
            _make_analysis_result("Frame 1 desc"),
            _make_analysis_result("Frame 2 desc"),
        ]
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_prov

        with _patch_security(tmp_path), \
             patch('vision_mcp.server.registry', mock_registry), \
             patch('vision_mcp.server.load_video', new_callable=AsyncMock,
                   return_value=video_payload):

            result = await analyze_video(
                source=str(test_file),
                prompt="Describe this video",
                max_frames=2,
            )

            assert "Frame 1 desc" in result
            assert "Frame 2 desc" in result


# ---------------------------------------------------------------------------
# ocr_image
# ---------------------------------------------------------------------------


class TestOCRImage:
    """Test ocr_image tool."""

    @pytest.mark.asyncio
    async def test_ocr_image(self, tmp_path):
        """OCR returns extracted text."""
        from PIL import Image

        test_file = tmp_path / "text.jpg"
        Image.new('RGB', (100, 100), color='white').save(test_file, 'JPEG')

        mock_prov = _mock_provider("Extracted text content")
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_prov

        with _patch_security(tmp_path), \
             patch('vision_mcp.server.registry', mock_registry), \
             patch('vision_mcp.server.load_image', new_callable=AsyncMock,
                   return_value=_make_image_payload()):

            result = await ocr_image(source=str(test_file))

            assert result == "Extracted text content"


# ---------------------------------------------------------------------------
# get_supported_formats
# ---------------------------------------------------------------------------


class TestGetSupportedFormats:
    """Test get_supported_formats tool."""

    @pytest.mark.asyncio
    async def test_get_formats(self):
        """Returns format information."""
        result = await get_supported_formats()

        assert "JPEG" in result
        assert "PNG" in result
        assert "MP4" in result
        assert "AVI" in result


# ---------------------------------------------------------------------------
# get_server_status
# ---------------------------------------------------------------------------


class TestGetServerStatus:
    """Test get_server_status tool."""

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Returns server configuration info."""
        result = await get_server_status()

        assert "Vision MCP Server" in result
        assert "Version" in result
