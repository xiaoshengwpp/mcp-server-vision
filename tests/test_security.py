"""Tests for security module."""

import os
import pytest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from vision_mcp.security import (
    SecurityConfig,
    validate_local_path,
    validate_url,
    check_file_size,
    check_file_size_stream,
    validate_mime_type,
    check_image_pixels,
    validate_file,
    SecurityError,
    PathTraversalError,
    SSRFError,
    FileSizeError,
    MimeTypeError,
    ImagePixelError,
    _is_private_ip,
    _detect_mime_from_bytes,
    DEFAULT_MAX_FILE_SIZE,
)


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------


class TestValidateLocalPath:
    """Test local path traversal protection."""

    def test_allowed_path(self, tmp_path):
        """Files inside allowed directories are accepted."""
        test_file = tmp_path / "test.jpg"
        test_file.touch()

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = validate_local_path(str(test_file), config=config)
        assert result == test_file.resolve()

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal with ../ is blocked."""
        test_file = tmp_path / "test.jpg"
        test_file.touch()

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        malicious = str(test_file) + "/../../../etc/passwd"
        with pytest.raises(PathTraversalError):
            validate_local_path(malicious, config=config)

    def test_outside_allowed_dir(self, tmp_path):
        """Paths outside allowed directories are rejected."""
        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        with pytest.raises(PathTraversalError):
            validate_local_path("/etc/passwd", config=config)

    def test_default_config_allows_home(self):
        """Default config allows files under home directory."""
        config = SecurityConfig()
        home = str(Path.home())
        assert any(home in p for p in config.allowed_paths)

    def test_symlink_followed_and_checked(self, tmp_path):
        """Symlinks are resolved and the target is validated."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("secret")

        link_dir = tmp_path / "links"
        link_dir.mkdir()
        link = link_dir / "link.txt"
        link.symlink_to(real_file)

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = validate_local_path(str(link), config=config)
        assert result == real_file.resolve()

    def test_symlink_outside_blocked(self, tmp_path):
        """Symlinks pointing outside allowed dirs are blocked."""
        link = tmp_path / "evil_link"
        link.symlink_to("/etc/passwd")

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        with pytest.raises(PathTraversalError):
            validate_local_path(str(link), config=config)

    def test_error_does_not_leak_allowed_paths(self, tmp_path):
        """Error messages should not reveal the allowed paths list."""
        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        with pytest.raises(PathTraversalError) as exc_info:
            validate_local_path("/etc/passwd", config=config)
        assert str(tmp_path) not in str(exc_info.value)


# ---------------------------------------------------------------------------
# URL / SSRF validation
# ---------------------------------------------------------------------------


class TestValidateURL:
    """Test URL SSRF protection."""

    def test_valid_https_url(self):
        """Valid HTTPS URLs are accepted."""
        url = "https://example.com/image.jpg"
        with patch('vision_mcp.security._resolve_host', return_value=["93.184.216.34"]):
            assert validate_url(url) == url

    def test_valid_http_url(self):
        """Valid HTTP URLs are accepted."""
        url = "http://example.com/image.jpg"
        with patch('vision_mcp.security._resolve_host', return_value=["93.184.216.34"]):
            assert validate_url(url) == url

    def test_localhost_blocked(self):
        """localhost is blocked via DNS resolution."""
        with pytest.raises(SSRFError):
            validate_url("http://localhost/image.jpg")

    def test_127_0_0_1_blocked(self):
        """127.0.0.1 is blocked via DNS resolution."""
        with pytest.raises(SSRFError):
            validate_url("http://127.0.0.1/image.jpg")

    def test_private_ip_192_blocked(self):
        """192.168.x.x private IPs are blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://192.168.1.1/image.jpg")

    def test_private_ip_10_blocked(self):
        """10.x.x.x private IPs are blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://10.0.0.1/image.jpg")

    def test_private_ip_172_blocked(self):
        """172.16.x.x private IPs are blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://172.16.0.1/image.jpg")

    def test_ftp_scheme_rejected(self):
        """Non-HTTP schemes are rejected."""
        with pytest.raises(SSRFError, match="scheme"):
            validate_url("ftp://example.com/image.jpg")

    def test_file_scheme_rejected(self):
        """file:// scheme is rejected."""
        with pytest.raises(SSRFError, match="scheme"):
            validate_url("file:///etc/passwd")

    def test_aws_metadata_blocked(self):
        """AWS metadata endpoint is blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_gcp_metadata_blocked(self):
        """GCP metadata endpoint is blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_ipv6_loopback_blocked(self):
        """IPv6 loopback [::1] is blocked."""
        with pytest.raises(SSRFError):
            validate_url("http://[::1]/image.jpg")

    def test_blocked_host_in_config(self):
        """Hosts in config.blocked_hosts are rejected."""
        config = SecurityConfig(blocked_hosts=frozenset({"evil.com"}))
        with pytest.raises(SSRFError, match="blocked"):
            validate_url("http://evil.com/image.jpg", config=config)

    def test_unresolvable_host_blocked(self):
        """Hosts that can't be resolved are rejected."""
        with pytest.raises(SSRFError, match="resolve"):
            validate_url("http://this-host-does-not-exist-12345.invalid/image.jpg")


# ---------------------------------------------------------------------------
# Private IP detection
# ---------------------------------------------------------------------------


class TestIsPrivateIP:
    """Test IP classification."""

    def test_loopback(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_private_192(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_private_10(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_invalid_ip_is_private(self):
        """Unparseable IPs are treated as private (defensive)."""
        assert _is_private_ip("not-an-ip") is True


# ---------------------------------------------------------------------------
# File size
# ---------------------------------------------------------------------------


class TestCheckFileSize:
    """Test file size enforcement."""

    def test_small_file_accepted(self, tmp_path):
        test_file = tmp_path / "small.jpg"
        test_file.write_bytes(b"x" * 1024)
        assert check_file_size(test_file) == 1024

    def test_large_file_rejected(self, tmp_path):
        test_file = tmp_path / "large.jpg"
        test_file.write_bytes(b"x" * 2048)
        with pytest.raises(FileSizeError):
            check_file_size(test_file, max_size=1024)

    def test_stream_size_check(self):
        data = b"x" * 200
        stream = BytesIO(data)
        with pytest.raises(FileSizeError):
            check_file_size_stream(stream, max_size=100)

    def test_stream_within_limit(self):
        data = b"x" * 50
        stream = BytesIO(data)
        result = check_file_size_stream(stream, max_size=100)
        assert result == data


# ---------------------------------------------------------------------------
# MIME type validation
# ---------------------------------------------------------------------------


class TestValidateMimeType:
    """Test MIME type detection and enforcement."""

    def test_valid_jpeg(self, tmp_path):
        from PIL import Image
        test_file = tmp_path / "test.jpg"
        Image.new('RGB', (10, 10), color='red').save(test_file, 'JPEG')
        mime = validate_mime_type(test_file)
        assert mime == "image/jpeg"

    def test_valid_png(self, tmp_path):
        from PIL import Image
        test_file = tmp_path / "test.png"
        Image.new('RGB', (10, 10), color='blue').save(test_file, 'PNG')
        mime = validate_mime_type(test_file)
        assert mime == "image/png"

    def test_text_file_rejected(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, world!")
        with pytest.raises(MimeTypeError):
            validate_mime_type(test_file)


# ---------------------------------------------------------------------------
# Image pixel count
# ---------------------------------------------------------------------------


class TestCheckImagePixels:
    """Test image pixel-count limits."""

    def test_small_image_accepted(self, tmp_path):
        from PIL import Image
        test_file = tmp_path / "small.jpg"
        Image.new('RGB', (100, 100), color='red').save(test_file, 'JPEG')
        w, h = check_image_pixels(test_file)
        assert w == 100 and h == 100

    def test_large_image_rejected(self, tmp_path):
        from PIL import Image
        test_file = tmp_path / "large.jpg"
        Image.new('RGB', (5000, 5000), color='red').save(test_file, 'JPEG')
        with pytest.raises(ImagePixelError):
            check_image_pixels(test_file, max_pixels=1_000_000)


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------


class TestValidateFile:
    """Test the full validation pipeline."""

    def test_valid_image(self, tmp_path):
        from PIL import Image
        test_file = tmp_path / "test.jpg"
        Image.new('RGB', (100, 100), color='red').save(test_file, 'JPEG')

        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        result = validate_file(test_file, config=config)
        assert result.path == test_file.resolve()
        assert result.mime_type == "image/jpeg"
        assert result.file_size > 0
        assert result.image_size == (100, 100)

    def test_invalid_path(self, tmp_path):
        config = SecurityConfig(allowed_paths=[str(tmp_path)])
        with pytest.raises(PathTraversalError):
            validate_file("/etc/passwd", config=config)


# ---------------------------------------------------------------------------
# MIME detection from bytes (ftyp brand disambiguation)
# ---------------------------------------------------------------------------


class TestDetectMimeFromBytes:
    """Test magic-byte MIME detection, especially ftyp brand handling."""

    def test_jpeg(self):
        header = b"\xff\xd8\xff" + b"\x00" * 29
        assert _detect_mime_from_bytes(header) == "image/jpeg"

    def test_png(self):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
        assert _detect_mime_from_bytes(header) == "image/png"

    def test_gif87(self):
        header = b"GIF87a" + b"\x00" * 26
        assert _detect_mime_from_bytes(header) == "image/gif"

    def test_gif89(self):
        header = b"GIF89a" + b"\x00" * 26
        assert _detect_mime_from_bytes(header) == "image/gif"

    def test_webp(self):
        header = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) == "image/webp"

    def test_riff_non_webp(self):
        """RIFF without WEBP brand is not detected as webp."""
        header = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 16
        assert _detect_mime_from_bytes(header) is None

    def test_heic_brand(self):
        """ftyp box with heic brand → image/heic."""
        header = b"\x00\x00\x00\x14ftypheic" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) == "image/heic"

    def test_avif_brand(self):
        """ftyp box with avif brand → image/avif."""
        header = b"\x00\x00\x00\x14ftypavif" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) == "image/avif"

    def test_mif1_brand(self):
        """ftyp box with mif1 brand → image/heif."""
        header = b"\x00\x00\x00\x14ftypmif1" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) == "image/heif"

    def test_mp4_brand_not_image(self):
        """ftyp box with mp42 brand is NOT detected as any image type."""
        header = b"\x00\x00\x00\x14ftypmp42" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) is None

    def test_mov_brand_not_image(self):
        """ftyp box with qt   brand (QuickTime/MOV) is NOT an image."""
        header = b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 16
        assert _detect_mime_from_bytes(header) is None

    def test_unknown_brand_not_image(self):
        """ftyp box with unknown brand returns None."""
        header = b"\x00\x00\x00\x14ftypXXXX" + b"\x00" * 16
        assert _detect_mime_from_bytes(header) is None

    def test_bmp(self):
        header = b"BM" + b"\x00" * 30
        assert _detect_mime_from_bytes(header) == "image/bmp"

    def test_tiff_little_endian(self):
        header = b"II\x2a\x00" + b"\x00" * 28
        assert _detect_mime_from_bytes(header) == "image/tiff"

    def test_tiff_big_endian(self):
        header = b"MM\x00\x2a" + b"\x00" * 28
        assert _detect_mime_from_bytes(header) == "image/tiff"

    def test_unknown_bytes(self):
        header = b"\x00\x01\x02\x03" + b"\x00" * 28
        assert _detect_mime_from_bytes(header) is None

    def test_short_header(self):
        """Header shorter than expected doesn't crash."""
        assert _detect_mime_from_bytes(b"\xff") is None
        assert _detect_mime_from_bytes(b"") is None
