"""Tests for media loading module."""

import base64
import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from PIL import Image

from vision_mcp.media import (
    ImagePayload,
    VideoPayload,
    VideoFrame,
    load_image,
    _load_image_from_file,
    _guess_mime,
    _is_url,
    _needs_downsampling,
    _downsample_image,
    _encode_image_base64,
    _format_for_mime,
    _check_stream_size,
    MediaError,
    ImageDecodeError,
)
from vision_mcp.security import (
    SecurityConfig,
    FileSizeError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_image(path: Path, fmt: str = "JPEG", size: tuple = (100, 100)):
    """Create a test image file."""
    img = Image.new('RGB', size, color='red')
    img.save(path, fmt)


# ---------------------------------------------------------------------------
# ImagePayload
# ---------------------------------------------------------------------------


class TestImagePayload:
    """Test ImagePayload dataclass."""

    def test_to_data_uri(self):
        payload = ImagePayload(
            data="dGVzdA==",
            mime_type="image/jpeg",
            width=100,
            height=100,
        )
        assert payload.to_data_uri() == "data:image/jpeg;base64,dGVzdA=="

    def test_frozen(self):
        payload = ImagePayload(
            data="dGVzdA==",
            mime_type="image/jpeg",
            width=100,
            height=100,
        )
        with pytest.raises(AttributeError):
            payload.data = "other"


# ---------------------------------------------------------------------------
# VideoFrame / VideoPayload
# ---------------------------------------------------------------------------


class TestVideoPayload:
    """Test video dataclasses."""

    def test_has_frames(self):
        empty = VideoPayload()
        assert empty.has_frames() is False

        with_frames = VideoPayload(frames=[VideoFrame(data="x")])
        assert with_frames.has_frames() is True


# ---------------------------------------------------------------------------
# MIME helpers
# ---------------------------------------------------------------------------


class TestGuessMime:
    """Test MIME type guessing from paths."""

    def test_jpg(self):
        assert _guess_mime("photo.jpg") == "image/jpeg"

    def test_jpeg(self):
        assert _guess_mime("photo.jpeg") == "image/jpeg"

    def test_png(self):
        assert _guess_mime("image.png") == "image/png"

    def test_gif(self):
        assert _guess_mime("anim.gif") == "image/gif"

    def test_mp4(self):
        assert _guess_mime("video.mp4") == "video/mp4"

    def test_unknown(self):
        # Unknown extension may return None or a guessed type
        result = _guess_mime("file.xyz123")
        assert result is None or isinstance(result, str)


class TestIsUrl:
    """Test URL detection heuristic."""

    def test_http(self):
        assert _is_url("http://example.com/img.jpg") is True

    def test_https(self):
        assert _is_url("https://example.com/img.jpg") is True

    def test_local_path(self):
        assert _is_url("/home/user/image.jpg") is False

    def test_relative_path(self):
        assert _is_url("./image.jpg") is False

    def test_ftp_not_url(self):
        assert _is_url("ftp://server.com/file.jpg") is False


# ---------------------------------------------------------------------------
# Image processing helpers
# ---------------------------------------------------------------------------


class TestImageHelpers:
    """Test image processing utilities."""

    def test_needs_downsampling_true(self):
        img = Image.new('RGB', (5000, 3000))
        assert _needs_downsampling(img, max_dimension=4096) is True

    def test_needs_downsampling_false(self):
        img = Image.new('RGB', (100, 100))
        assert _needs_downsampling(img, max_dimension=4096) is False

    def test_downsample_preserves_aspect_ratio(self):
        img = Image.new('RGB', (8000, 4000))
        result = _downsample_image(img, max_dimension=4096)
        assert result.size[0] == 4096
        assert result.size[1] == 2048

    def test_downsample_noop_when_small(self):
        img = Image.new('RGB', (100, 100))
        result = _downsample_image(img, max_dimension=4096)
        assert result.size == (100, 100)

    def test_encode_jpeg(self):
        img = Image.new('RGB', (10, 10), color='blue')
        b64 = _encode_image_base64(img, fmt="JPEG")
        decoded = base64.b64decode(b64)
        # Verify it's valid JPEG
        assert decoded[:3] == b"\xff\xd8\xff"

    def test_encode_png_with_alpha(self):
        img = Image.new('RGBA', (10, 10), color=(255, 0, 0, 128))
        b64 = _encode_image_base64(img, fmt="JPEG")
        # Should convert to RGB for JPEG
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_format_for_mime(self):
        assert _format_for_mime("image/jpeg") == "JPEG"
        assert _format_for_mime("image/png") == "PNG"
        assert _format_for_mime("image/heic") == "JPEG"  # fallback
        assert _format_for_mime("unknown/type") == "PNG"  # default


# ---------------------------------------------------------------------------
# Stream size check
# ---------------------------------------------------------------------------


class TestCheckStreamSize:
    """Test streaming size enforcement."""

    def test_within_limit(self):
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"x" * 50, b"x" * 30]
        result = _check_stream_size(mock_resp, max_size=100)
        assert len(result) == 80

    def test_exceeds_limit(self):
        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"x" * 60, b"x" * 60]
        with pytest.raises(FileSizeError):
            _check_stream_size(mock_resp, max_size=100)


# ---------------------------------------------------------------------------
# Local image loading
# ---------------------------------------------------------------------------


class TestLoadImageFromFile:
    """Test local image loading with security validation."""

    def test_load_local_jpeg(self, tmp_path):
        """Load a real JPEG file and get an ImagePayload back."""
        test_file = tmp_path / "test.jpg"
        _create_test_image(test_file, "JPEG", (200, 150))

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = _load_image_from_file(str(test_file), config=config)

        assert isinstance(result, ImagePayload)
        assert result.mime_type == "image/jpeg"
        assert result.width == 200
        assert result.height == 150
        assert result.downsampled is False
        assert len(result.data) > 0

    def test_load_local_png(self, tmp_path):
        """Load a real PNG file."""
        test_file = tmp_path / "test.png"
        _create_test_image(test_file, "PNG", (50, 50))

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = _load_image_from_file(str(test_file), config=config)

        assert result.mime_type == "image/png"
        assert result.width == 50

    def test_downsampling_applied(self, tmp_path):
        """Large images are downsampled when threshold is exceeded."""
        test_file = tmp_path / "large.jpg"
        _create_test_image(test_file, "JPEG", (5000, 3000))

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = _load_image_from_file(
            str(test_file),
            config=config,
            max_dimension=4096,
        )

        assert result.downsampled is True
        assert result.width == 5000  # original dimensions preserved in payload
        assert result.height == 3000


# ---------------------------------------------------------------------------
# Unified loader
# ---------------------------------------------------------------------------


class TestLoadImage:
    """Test the unified load_image function."""

    @pytest.mark.asyncio
    async def test_local_image(self, tmp_path):
        """Local path detection and loading works."""
        test_file = tmp_path / "test.jpg"
        _create_test_image(test_file)

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = await load_image(str(test_file), config=config)

        assert isinstance(result, ImagePayload)
        assert result.source == str(test_file.resolve())


# ---------------------------------------------------------------------------
# URL loading (mocked HTTP)
# ---------------------------------------------------------------------------


class TestLoadImageFromUrl:
    """Test image loading from URLs with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_load_jpeg_from_url(self):
        """Load a JPEG image from a URL."""
        from vision_mcp.media import _load_image_from_url

        # Create a real JPEG in memory
        buf = io.BytesIO()
        Image.new('RGB', (200, 150), color='blue').save(buf, 'JPEG')
        jpeg_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.url = "https://example.com/photo.jpg"
        mock_resp.iter_bytes.return_value = [jpeg_bytes]
        mock_resp.raise_for_status = MagicMock()

        with patch('vision_mcp.media.validate_url', return_value="https://example.com/photo.jpg"), \
             patch('vision_mcp.media.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            result = await _load_image_from_url("https://example.com/photo.jpg")

            assert isinstance(result, ImagePayload)
            assert result.mime_type == "image/jpeg"
            assert result.width == 200
            assert result.height == 150
            assert result.source == "https://example.com/photo.jpg"

    @pytest.mark.asyncio
    async def test_load_png_from_url_with_charset(self):
        """Content-Type with charset suffix is handled correctly."""
        from vision_mcp.media import _load_image_from_url

        buf = io.BytesIO()
        Image.new('RGB', (50, 50), color='green').save(buf, 'PNG')
        png_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/png; charset=utf-8"}
        mock_resp.url = "https://example.com/icon.png"
        mock_resp.iter_bytes.return_value = [png_bytes]
        mock_resp.raise_for_status = MagicMock()

        with patch('vision_mcp.media.validate_url', return_value="https://example.com/icon.png"), \
             patch('vision_mcp.media.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            result = await _load_image_from_url("https://example.com/icon.png")

            assert result.mime_type == "image/png"

    @pytest.mark.asyncio
    async def test_too_many_redirects_raises(self):
        """Exceeding max redirects raises MediaError."""
        from vision_mcp.media import _load_bytes_from_url

        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"location": "https://example.com/next"}

        with patch('vision_mcp.media.validate_url', return_value="https://example.com/start"), \
             patch('vision_mcp.media.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = redirect_resp

            with pytest.raises(MediaError, match="Too many redirects"):
                await _load_bytes_from_url(
                    "https://example.com/start",
                    max_redirects=3,
                )

    @pytest.mark.asyncio
    async def test_redirect_missing_location_raises(self):
        """302 without Location header raises MediaError."""
        from vision_mcp.media import _load_bytes_from_url

        bad_redirect = MagicMock()
        bad_redirect.status_code = 302
        bad_redirect.headers = {}  # no Location

        with patch('vision_mcp.media.validate_url', return_value="https://example.com/start"), \
             patch('vision_mcp.media.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = bad_redirect

            with pytest.raises(MediaError, match="missing Location"):
                await _load_bytes_from_url("https://example.com/start")

    @pytest.mark.asyncio
    async def test_oversized_remote_file_rejected(self):
        """Remote file exceeding size limit is rejected."""
        from vision_mcp.media import _load_bytes_from_url

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.iter_bytes.return_value = [b"x" * 200]
        mock_resp.raise_for_status = MagicMock()

        with patch('vision_mcp.media.validate_url', return_value="https://example.com/huge.jpg"), \
             patch('vision_mcp.media.httpx.AsyncClient') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            config = SecurityConfig()
            config.max_file_size = 100  # very small limit

            with pytest.raises(FileSizeError):
                await _load_bytes_from_url(
                    "https://example.com/huge.jpg",
                    config=config,
                )


# ---------------------------------------------------------------------------
# load_media auto-detection
# ---------------------------------------------------------------------------


class TestLoadMedia:
    """Test the unified load_media function (image vs video detection)."""

    @pytest.mark.asyncio
    async def test_image_detected(self, tmp_path):
        """Non-video extension loads as image."""
        from vision_mcp.media import load_media

        test_file = tmp_path / "photo.jpg"
        _create_test_image(test_file)

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = await load_media(str(test_file), config=config)
        assert isinstance(result, ImagePayload)

    @pytest.mark.asyncio
    async def test_video_extension_detected(self, tmp_path):
        """Video extension triggers video loading path."""
        from vision_mcp.media import load_media

        test_file = tmp_path / "clip.mp4"
        test_file.write_bytes(b"fake video data")

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        # Video loading will fail on fake data, but we just test routing
        result = await load_media(str(test_file), config=config, num_frames=0)
        assert isinstance(result, VideoPayload)


# ---------------------------------------------------------------------------
# VideoPayload / VideoFrame dataclasses
# ---------------------------------------------------------------------------


class TestVideoFrame:
    """Test VideoFrame dataclass."""

    def test_defaults(self):
        frame = VideoFrame(data="dGVzdA==")
        assert frame.mime_type == "image/jpeg"
        assert frame.timestamp_sec == 0.0
        assert frame.frame_index == 0

    def test_custom_values(self):
        frame = VideoFrame(
            data="dGVzdA==",
            mime_type="image/png",
            timestamp_sec=5.5,
            frame_index=42,
        )
        assert frame.timestamp_sec == 5.5
        assert frame.frame_index == 42
