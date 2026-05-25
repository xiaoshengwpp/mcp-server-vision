"""
Security module for Vision MCP Server.

Provides:
  - Local path traversal protection (allowlist-based)
  - URL SSRF protection (blocks loopback, private, link-local, cloud metadata)
  - File size limits
  - MIME type validation
  - Image pixel-count limits
"""

from __future__ import annotations

import ipaddress
import mimetypes
import os
import re
import socket
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from PIL import Image

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_IMAGE_PIXELS = 50_000_000       # 50 MP
DEFAULT_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "image/heic",
        "image/heif",
        "image/avif",
        "application/octet-stream",  # fallback; validated by magic bytes
    }
)

# Cloud provider metadata endpoints (SSRF targets)
_CLOUD_METADATA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(https?://)?169\.254\.169\.254", re.IGNORECASE),      # AWS / GCP / Azure
    re.compile(r"^(https?://)?metadata\.google\.internal", re.IGNORECASE),  # GCP
    re.compile(r"^(https?://)?metadata\.azure\.tlds?", re.IGNORECASE),      # Azure
    re.compile(r"^(https?://)?aliyun\.oxs", re.IGNORECASE),                 # Alibaba Cloud
    re.compile(r"^(https?://)?100\.100\.100\.200", re.IGNORECASE),          # Alibaba Cloud
]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Base exception for security violations."""


class PathTraversalError(SecurityError):
    """Raised when a path escapes the allowed base directories."""


class SSRFError(SecurityError):
    """Raised when a URL targets an internal/cloud-metadata endpoint."""


class FileSizeError(SecurityError):
    """Raised when a file exceeds the configured size limit."""


class MimeTypeError(SecurityError):
    """Raised when a file's MIME type is not in the allowed set."""


class ImagePixelError(SecurityError):
    """Raised when an image exceeds the maximum pixel count."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SecurityConfig:
    """Security policy configuration."""

    # Path allowlist – only files under these directories are accessible.
    allowed_paths: list[str] = field(
        default_factory=lambda: [str(Path.home())]
    )

    # File size ceiling (bytes).
    max_file_size: int = DEFAULT_MAX_FILE_SIZE

    # Image pixel ceiling (width × height).
    max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS

    # Allowed MIME types.
    allowed_mime_types: frozenset[str] = DEFAULT_ALLOWED_MIME_TYPES

    # Block DNS-rebinding by requiring resolved IPs to stay non-internal.
    block_private_ips: bool = True

    # Extra hostnames to always block (e.g. internal hostnames).
    blocked_hosts: frozenset[str] = field(
        default_factory=frozenset[str],
        repr=False,
    )

    def __post_init__(self) -> None:
        # Normalise allowed paths to absolute resolved strings.
        self.allowed_paths = [
            str(Path(p).resolve()) for p in self.allowed_paths
        ]

    def to_allowed_paths(self) -> list[Path]:
        return [Path(p) for p in self.allowed_paths]


# ---------------------------------------------------------------------------
# Path-traversal guard
# ---------------------------------------------------------------------------

def validate_local_path(
    requested: str | Path,
    *,
    config: SecurityConfig | None = None,
) -> Path:
    """
    Resolve *requested* to an absolute path and verify it is inside at
    least one of ``config.allowed_paths``.

    Path.resolve() follows symlinks, so the resolved target is always
    checked against allowed paths — symlink-based escapes are blocked.

    Raises ``PathTraversalError`` on violation.
    """
    config = config or SecurityConfig()
    target = Path(requested).resolve()

    for base in config.to_allowed_paths():
        try:
            target.relative_to(base)
            return target
        except ValueError:
            continue

    raise PathTraversalError(
        f"Path '{requested}' is outside allowed directories."
    )


# ---------------------------------------------------------------------------
# IP / SSRF helpers
# ---------------------------------------------------------------------------

def _is_private_ip(ip_str: str) -> bool:
    """Return ``True`` when *ip_str* is a non-routable / internal address."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → block defensively
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _resolve_host(host: str) -> list[str]:
    """Resolve hostname to IP addresses (IPv4 + IPv6)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for family, _, _, _, sockaddr in infos:
        ip = str(sockaddr[0])
        if ip not in seen:
            seen.add(ip)
            result.append(ip)
    return result


def _matches_cloud_metadata(url: str) -> bool:
    """Check if URL points to a known cloud metadata endpoint."""
    for pattern in _CLOUD_METADATA_PATTERNS:
        if pattern.search(url):
            return True
    return False


def validate_url(
    url: str,
    *,
    config: SecurityConfig | None = None,
) -> str:
    """
    Validate *url* is safe for server-side fetching.

    Checks performed:
      1. Scheme must be http or https.
      2. Host must not be in the blocked list.
      3. Resolved IP(s) must not be private/internal (if ``block_private_ips``).
      4. Must not match cloud-metadata patterns.
      5. No IPv6-literal loopback or link-local.

    Raises ``SSRFError`` on violation.  Returns the original URL on success.
    """
    config = config or SecurityConfig()
    config_block = config.block_private_ips

    parsed = urllib.parse.urlparse(url)

    # 1. Scheme check
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' is not allowed; use http or https."
        )

    host = parsed.hostname or ""
    if not host:
        raise SSRFError("URL has no hostname.")

    # 2. Blocked host check
    if host in config.blocked_hosts:
        raise SSRFError(f"Host '{host}' is explicitly blocked.")

    # 3. Cloud-metadata pattern check (before DNS resolution catches aliases)
    if _matches_cloud_metadata(url):
        raise SSRFError(
            f"URL targets a cloud metadata endpoint: '{url}'"
        )

    # 4. DNS resolution + IP-range check
    if config_block:
        ips = _resolve_host(host)
        if not ips:
            raise SSRFError(f"Could not resolve host '{host}'.")
        for ip in ips:
            if _is_private_ip(ip):
                raise SSRFError(
                    f"Host '{host}' resolves to private/internal IP '{ip}'."
                )

    # 5. IPv6 literal edge-cases in the raw netloc
    netloc = parsed.netloc.lower()
    if "[::1]" in netloc or "[fe80:" in netloc:
        raise SSRFError(f"URL contains loopback/link-local IPv6 literal: '{url}'")

    return url


# ---------------------------------------------------------------------------
# File-size guard
# ---------------------------------------------------------------------------

def check_file_size(
    path: str | Path,
    *,
    max_size: int | None = None,
    config: SecurityConfig | None = None,
) -> int:
    """
    Verify that the file at *path* does not exceed *max_size* bytes.

    Returns the file size on success.  Raises ``FileSizeError`` on violation.
    """
    if config:
        max_size = config.max_file_size
    max_size = max_size or DEFAULT_MAX_FILE_SIZE

    size = os.path.getsize(path)
    if size > max_size:
        raise FileSizeError(
            f"File size {size:,} bytes exceeds limit of {max_size:,} bytes."
        )
    return size


def check_file_size_stream(
    readable: IO[bytes],  # file-like object with .read()
    *,
    max_size: int | None = None,
    config: SecurityConfig | None = None,
    chunk_size: int = 64 * 1024,
) -> bytes:
    """
    Read from *readable* in chunks, aborting if total bytes exceed *max_size*.

    Returns the collected bytes.  Raises ``FileSizeError`` on violation.
    Useful for streaming HTTP responses where Content-Length is absent or
    untrusted.
    """
    if config:
        max_size = config.max_file_size
    max_size = max_size or DEFAULT_MAX_FILE_SIZE

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = readable.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise FileSizeError(
                f"Stream size exceeds limit of {max_size:,} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# MIME-type validation
# ---------------------------------------------------------------------------

# Quick magic-byte map for common image formats.
_IMAGE_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),       # webp starts with RIFF
    (b"BM", "image/bmp"),
    (b"II\x2a\x00", "image/tiff"),  # little-endian TIFF
    (b"MM\x00\x2a", "image/tiff"),  # big-endian TIFF
    (b"\x00\x00\x00\x0cJXL", "image/jxl"),
]

# ISOBMFF (ftyp) brand → MIME mapping.
# The brand is at bytes 8–12 of the file (after box size + "ftyp").
# HEIC/HEIF, AVIF, and video formats all share the ftyp container;
# only image brands are listed here — video brands are intentionally
# excluded so that MP4/MOV files are not misidentified as images.
_FTYPE_BRAND_MIME: dict[bytes, str] = {
    b"heic": "image/heic",
    b"heix": "image/heic",
    b"hevc": "image/heic",
    b"mif1": "image/heif",
    b"msf1": "image/heif",
    b"avif": "image/avif",
    b"avis": "image/avif",
}


def _detect_mime_from_bytes(header: bytes) -> str | None:
    """Attempt MIME detection from file header bytes (first 32 bytes)."""
    for magic, mime in _IMAGE_MAGIC_BYTES:
        if header.startswith(magic):
            # webp needs a deeper check: RIFF....WEBP
            if mime == "image/webp":
                if len(header) >= 12 and header[8:12] == b"WEBP":
                    return mime
                return None
            return mime

    # ISOBMFF / ftyp container — check brand to distinguish HEIC/AVIF
    # from MP4/MOV (which share the same ftyp box structure).
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        return _FTYPE_BRAND_MIME.get(brand)

    return None


def validate_mime_type(
    path: str | Path,
    *,
    allowed: frozenset[str] | None = None,
    config: SecurityConfig | None = None,
) -> str:
    """
    Validate the MIME type of the file at *path*.

    Uses magic-byte sniffing first (most reliable), falls back to
    ``mimetypes.guess_type``.  The detected type must be in *allowed*.

    Returns the detected MIME type on success.
    Raises ``MimeTypeError`` on violation.
    """
    if config:
        allowed = config.allowed_mime_types
    allowed = allowed or DEFAULT_ALLOWED_MIME_TYPES

    path = Path(path)

    # Magic-byte sniffing (read first 32 bytes)
    detected: str | None = None
    with open(path, "rb") as fh:
        header = fh.read(32)

    detected = _detect_mime_from_bytes(header)

    # Fallback: extension-based guess
    if detected is None:
        guessed, _ = mimetypes.guess_type(str(path))
        if guessed:
            detected = guessed

    if detected is None:
        raise MimeTypeError(
            f"Could not determine MIME type for '{path}'."
        )

    if detected not in allowed:
        raise MimeTypeError(
            f"MIME type '{detected}' is not allowed for '{path}'. "
            f"Allowed: {sorted(allowed)}"
        )

    return detected


# ---------------------------------------------------------------------------
# Image pixel-count guard
# ---------------------------------------------------------------------------

def check_image_pixels(
    path: str | Path,
    *,
    max_pixels: int | None = None,
    config: SecurityConfig | None = None,
) -> tuple[int, int]:
    """
    Open the image at *path* and verify ``width × height <= max_pixels``.

    Uses PIL ``Image.open`` which reads only the header (no pixel decode).

    Returns ``(width, height)`` on success.
    Raises ``ImagePixelError`` on violation.
    """
    if config:
        max_pixels = config.max_image_pixels
    max_pixels = max_pixels or DEFAULT_MAX_IMAGE_PIXELS

    with Image.open(path) as img:
        w, h = img.size
        total = w * h
        if total > max_pixels:
            raise ImagePixelError(
                f"Image size {w}×{h} = {total:,} pixels exceeds limit "
                f"of {max_pixels:,} pixels."
            )
    return w, h


# ---------------------------------------------------------------------------
# Combined validation helper
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a full security validation pass."""

    path: Path
    file_size: int
    mime_type: str
    image_size: tuple[int, int] | None = None


def validate_file(
    requested: str | Path,
    *,
    config: SecurityConfig | None = None,
    is_image: bool = True,
) -> ValidationResult:
    """
    Run the full security validation pipeline on a local file:
      1. Path-traversal guard
      2. File-size check
      3. MIME-type validation
      4. Image pixel-count check (if ``is_image``)

    Returns a ``ValidationResult`` on success.
    Raises the appropriate ``SecurityError`` subclass on failure.
    """
    config = config or SecurityConfig()

    # 1. Path traversal
    resolved = validate_local_path(requested, config=config)

    # 2. File size
    size = check_file_size(resolved, config=config)

    # 3. MIME type
    mime = validate_mime_type(resolved, config=config)

    # 4. Image pixel check
    image_size: tuple[int, int] | None = None
    if is_image:
        image_size = check_image_pixels(resolved, config=config)

    return ValidationResult(
        path=resolved,
        file_size=size,
        mime_type=mime,
        image_size=image_size,
    )


def validate_remote_file(
    url: str,
    *,
    config: SecurityConfig | None = None,
) -> str:
    """
    Validate a URL for SSRF safety.  Intended to be called before the
    caller performs any HTTP fetch.

    Returns the validated URL string.
    """
    return validate_url(url, config=config or SecurityConfig())
