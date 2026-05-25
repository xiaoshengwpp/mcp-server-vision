"""
Media loading module for Vision MCP Server.

Provides async loading of images and videos from local paths and URLs,
with automatic base64 encoding, MIME detection, redirect following,
image downsampling, and optional video frame extraction.

Returns standardized ImagePayload / VideoPayload data structures.
"""

from __future__ import annotations

import base64
import io
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import httpx
from PIL import Image

from .security import (
    DEFAULT_MAX_FILE_SIZE,
    FileSizeError,
    MimeTypeError,
    SecurityConfig,
    SecurityError,
    ValidationResult,
    check_file_size,
    validate_file,
    validate_local_path,
    validate_remote_file,
    validate_url,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_IMAGE_DIMENSION = 4096  # max width or height before downsampling
DEFAULT_VIDEO_FRAME_COUNT = 1       # default frames to extract from video
DEFAULT_HTTP_TIMEOUT = 30.0         # seconds

# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImagePayload:
    """Standardized payload for a single image."""

    # base64-encoded image data (no data URI prefix)
    data: str

    # MIME type, e.g. "image/jpeg"
    mime_type: str

    # Original image dimensions (before any downsampling)
    width: int
    height: int

    # True if the image was downsampled from its original size
    downsampled: bool = False

    # Source path or URL
    source: str = ""

    # Extra metadata (file size, etc.)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_data_uri(self) -> str:
        """Return a data URI suitable for JSON/API transport."""
        return f"data:{self.mime_type};base64,{self.data}"


@dataclass(frozen=True)
class VideoFrame:
    """A single frame extracted from a video."""

    # base64-encoded JPEG/PNG frame data
    data: str
    mime_type: str = "image/jpeg"
    timestamp_sec: float = 0.0
    frame_index: int = 0


@dataclass(frozen=True)
class VideoPayload:
    """Standardized payload for a video."""

    # base64-encoded video data (full video, or empty if frame-only mode)
    data: Optional[str] = None
    mime_type: str = "video/mp4"
    source: str = ""
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    frames: List[VideoFrame] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def has_frames(self) -> bool:
        return len(self.frames) > 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MediaError(SecurityError):
    """Base exception for media loading errors."""


class ImageDecodeError(MediaError):
    """Raised when an image cannot be decoded."""


class VideoError(MediaError):
    """Raised when a video cannot be processed."""


# ---------------------------------------------------------------------------
# MIME helpers
# ---------------------------------------------------------------------------

_MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}


def _guess_mime(path_or_url: str) -> Optional[str]:
    """Guess MIME type from file extension or URL path."""
    parsed = Path(path_or_url)
    ext = parsed.suffix.lower()
    mime = _MIME_BY_EXT.get(ext)
    if mime:
        return mime
    guessed, _ = mimetypes.guess_type(str(path_or_url))
    return guessed


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def _needs_downsampling(
    img: Image.Image,
    *,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
) -> bool:
    """Return True if image exceeds the max dimension threshold."""
    w, h = img.size
    return w > max_dimension or h > max_dimension


def _downsample_image(
    img: Image.Image,
    *,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
) -> Image.Image:
    """Downsample image so that its longest side fits within max_dimension.

    Preserves aspect ratio.  Uses LANCZOS for high-quality scaling.
    """
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dimension:
        return img

    scale = max_dimension / longest
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _encode_image_base64(img: Image.Image, *, fmt: str = "JPEG") -> str:
    """Encode a PIL Image to base64 string.

    Converts to RGB for JPEG output, otherwise uses PNG for formats
    that support alpha.
    """
    buf = io.BytesIO()
    save_kwargs: dict[str, Any] = {}

    if fmt.upper() == "JPEG":
        # JPEG doesn't support alpha; convert to RGB
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = 85
    elif fmt.upper() in ("PNG",):
        save_kwargs["optimize"] = True
    else:
        save_kwargs["quality"] = 85

    img.save(buf, format=fmt, **save_kwargs)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _format_for_mime(mime_type: str) -> str:
    """Map MIME type to PIL save format name."""
    mapping = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/gif": "GIF",
        "image/webp": "WEBP",
        "image/bmp": "BMP",
        "image/tiff": "TIFF",
        "image/heic": "JPEG",  # PIL can't save HEIC; fallback to JPEG
        "image/heif": "JPEG",
        "image/avif": "PNG",  # fallback
    }
    return mapping.get(mime_type, "PNG")


# ---------------------------------------------------------------------------
# Local file loading
# ---------------------------------------------------------------------------


def _load_image_from_file(
    path: str | Path,
    *,
    config: Optional[SecurityConfig] = None,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    force_downsample: bool = False,
) -> ImagePayload:
    """Load and encode a local image file.

    Performs full security validation (path traversal, size, MIME, pixels).
    Optionally downsamples oversized images.
    """
    config = config or SecurityConfig()

    # Security validation
    validation = validate_file(path, config=config, is_image=True)

    with Image.open(validation.path) as img:
        original_size = img.size
        original_w, original_h = original_size
        downsampled = False

        # Clone for safety (PIL lazy loads)
        img.load()

        if force_downsample or _needs_downsampling(img, max_dimension=max_dimension):
            img = _downsample_image(img, max_dimension=max_dimension)
            downsampled = True

        fmt = _format_for_mime(validation.mime_type)
        b64_data = _encode_image_base64(img, fmt=fmt)

    return ImagePayload(
        data=b64_data,
        mime_type=validation.mime_type,
        width=original_w,
        height=original_h,
        downsampled=downsampled,
        source=str(validation.path),
        extra={"file_size": validation.file_size},
    )


# ---------------------------------------------------------------------------
# URL loading (async)
# ---------------------------------------------------------------------------


async def _load_bytes_from_url(
    url: str,
    *,
    config: Optional[SecurityConfig] = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> tuple[bytes, str, Optional[str]]:
    """Fetch bytes from a URL with redirect following and SSRF protection.

    Returns (raw_bytes, final_url, content_type).

    SSRF validation is performed on the original URL and on every
    redirect target.  Redirects to private/internal IPs are blocked.
    """
    config = config or SecurityConfig()

    # Pre-validate the initial URL
    validate_url(url, config=config)

    async with httpx.AsyncClient(
        follow_redirects=False,  # manual redirect control
        timeout=timeout,
        max_redirects=0,
    ) as client:
        current_url = url
        redirect_count = 0

        while True:
            # Validate each redirect hop
            validate_url(current_url, config=config)

            resp = await client.get(current_url)

            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise MediaError(
                        f"Too many redirects (>{max_redirects}) for URL: {url}"
                    )
                location = resp.headers.get("location")
                if not location:
                    raise MediaError(
                        f"Redirect response missing Location header for: {current_url}"
                    )
                # Resolve relative redirects
                current_url = str(httpx.URL(location).join(httpx.URL(current_url)))
                continue

            resp.raise_for_status()

            # Stream with size guard
            content = _check_stream_size(
                resp, max_size=config.max_file_size
            )
            content_type = resp.headers.get("content-type", "")
            # Strip charset suffix (e.g. "image/jpeg; charset=..." -> "image/jpeg")
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()
            return content, str(resp.url), content_type if content_type else None


def _check_stream_size(
    response: httpx.Response,
    *,
    max_size: int = DEFAULT_MAX_FILE_SIZE,
) -> bytes:
    """Read response body with streaming size enforcement."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_size:
            raise FileSizeError(
                f"Remote file size {total:,} bytes exceeds limit "
                f"of {max_size:,} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _load_image_from_url(
    url: str,
    *,
    config: Optional[SecurityConfig] = None,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> ImagePayload:
    """Load and encode an image from a URL.

    Fetches the image, detects MIME type, optionally downsamples,
    and returns an ImagePayload.
    """
    config = config or SecurityConfig()
    raw_bytes, final_url, content_type = await _load_bytes_from_url(
        url,
        config=config,
        max_redirects=max_redirects,
        timeout=timeout,
    )

    # MIME detection priority:
    # 1. Magic-byte sniffing from response body (most reliable)
    # 2. HTTP Content-Type header
    # 3. URL extension guess
    mime_type: Optional[str] = None

    header = raw_bytes[:32]
    from .security import _detect_mime_from_bytes
    mime_type = _detect_mime_from_bytes(header)

    if mime_type is None and content_type:
        mime_type = content_type

    if mime_type is None:
        mime_type = _guess_mime(url)

    if mime_type is None:
        mime_type = "image/png"  # safe default

    # Decode image
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()  # force decode
    except Exception as e:
        raise ImageDecodeError(f"Failed to decode image from {url}: {e}") from e

    original_size = img.size
    original_w, original_h = original_size
    downsampled = False

    if _needs_downsampling(img, max_dimension=max_dimension):
        img = _downsample_image(img, max_dimension=max_dimension)
        downsampled = True

    fmt = _format_for_mime(mime_type)
    b64_data = _encode_image_base64(img, fmt=fmt)

    return ImagePayload(
        data=b64_data,
        mime_type=mime_type,
        width=original_w,
        height=original_h,
        downsampled=downsampled,
        source=url,
        extra={"file_size": len(raw_bytes), "final_url": final_url},
    )


# ---------------------------------------------------------------------------
# Unified image loader
# ---------------------------------------------------------------------------


async def load_image(
    source: str,
    *,
    config: Optional[SecurityConfig] = None,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    force_downsample: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> ImagePayload:
    """Load an image from a local path or URL.

    Automatically detects whether *source* is a URL or local path.

    Args:
        source: Local file path or HTTP(S) URL.
        config: Optional security configuration.
        max_dimension: Maximum width or height before downsampling.
        force_downsample: Always downsample regardless of size.
        max_redirects: Maximum HTTP redirects to follow.
        timeout: HTTP request timeout in seconds.

    Returns:
        ImagePayload with base64-encoded image data.
    """
    config = config or SecurityConfig()

    if _is_url(source):
        return await _load_image_from_url(
            source,
            config=config,
            max_dimension=max_dimension,
            max_redirects=max_redirects,
            timeout=timeout,
        )
    else:
        return _load_image_from_file(
            source,
            config=config,
            max_dimension=max_dimension,
            force_downsample=force_downsample,
        )


def _is_url(source: str) -> bool:
    """Heuristic: source is a URL if it starts with http:// or https://."""
    return source.startswith(("http://", "https://"))


# ---------------------------------------------------------------------------
# Video helpers
# ---------------------------------------------------------------------------


def _extract_frames_opencv(
    path_or_url: str,
    *,
    num_frames: int = DEFAULT_VIDEO_FRAME_COUNT,
    is_url: bool = False,
    config: Optional[SecurityConfig] = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    raw_bytes: Optional[bytes] = None,
) -> list[VideoFrame]:
    """Extract frames from a video using OpenCV.

    Evenly distributes *num_frames* across the video timeline.
    Falls back gracefully if OpenCV is not installed.
    """
    import cv2

    # For URLs, download first
    video_path: str = path_or_url
    temp_file: Optional[str] = None

    if is_url and raw_bytes is None:
        raise VideoError("raw_bytes must be provided for URL-based video extraction")

    if is_url and raw_bytes is not None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False
        )
        tmp.write(raw_bytes)
        tmp.close()
        video_path = tmp.name
        temp_file = tmp.name

    frames: list[VideoFrame] = []

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise VideoError(f"Cannot open video: {path_or_url}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        if total_frames <= 0:
            cap.release()
            return frames

        # Evenly space frames across the video
        if num_frames >= total_frames:
            indices = list(range(total_frames))
        else:
            step = total_frames / num_frames
            indices = [int(i * step) for i in range(num_frames)]

        for frame_index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame_bgr = cap.read()
            if not ret:
                continue

            timestamp = frame_index / fps if fps > 0 else 0.0

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)

            # Downsample if needed
            if _needs_downsampling(pil_img):
                pil_img = _downsample_image(pil_img)

            b64_data = _encode_image_base64(pil_img, fmt="JPEG")

            frames.append(
                VideoFrame(
                    data=b64_data,
                    mime_type="image/jpeg",
                    timestamp_sec=timestamp,
                    frame_index=frame_index,
                )
            )

        cap.release()
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

    return frames


def _extract_frames_ffmpeg_fallback(
    video_path: str,
    *,
    num_frames: int = DEFAULT_VIDEO_FRAME_COUNT,
) -> list[VideoFrame]:
    """Fallback frame extraction using ffmpeg CLI (if available).

    Uses subprocess to call ffmpeg directly without OpenCV dependency.
    """
    import subprocess
    import tempfile
    import shutil

    if not shutil.which("ffmpeg"):
        raise VideoError(
            "Neither OpenCV nor ffmpeg is available for video processing."
        )

    frames: list[VideoFrame] = []
    tmp_dir = tempfile.mkdtemp(prefix="vision_mcp_frames_")

    try:
        # Get video info
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames,r_frame_rate",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Fallback: extract frames at fixed intervals
        # Use ffmpeg to extract N evenly-spaced frames
        subprocess.run(
            [
                "ffmpeg",
                "-i", video_path,
                "-vf", f"fps=1/60,scale=iw:ih",  # 1 frame per 60 seconds
                "-frames:v", str(num_frames),
                "-q:v", "2",
                f"{tmp_dir}/frame_%04d.jpg",
            ],
            capture_output=True,
            timeout=60,
        )

        # Read extracted frames
        frame_files = sorted(Path(tmp_dir).glob("frame_*.jpg"))
        for idx, fpath in enumerate(frame_files[:num_frames]):
            with open(fpath, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("ascii")
            frames.append(
                VideoFrame(
                    data=b64_data,
                    timestamp_sec=idx * 60.0,
                    frame_index=idx,
                )
            )

    except subprocess.TimeoutExpired:
        raise VideoError("ffmpeg/ffprobe timed out processing video.")
    finally:
        # Cleanup temp directory
        import shutil as _shutil
        _shutil.rmtree(tmp_dir, ignore_errors=True)

    return frames


async def load_video(
    source: str,
    *,
    config: Optional[SecurityConfig] = None,
    num_frames: int = DEFAULT_VIDEO_FRAME_COUNT,
    encode_full_video: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> VideoPayload:
    """Load a video from a local path or URL.

    Supports frame extraction via OpenCV (primary) or ffmpeg CLI (fallback).

    Args:
        source: Local file path or HTTP(S) URL.
        config: Optional security configuration.
        num_frames: Number of frames to extract.
        encode_full_video: If True, also base64-encode the full video file.
        max_redirects: Maximum HTTP redirects to follow.
        timeout: HTTP request timeout in seconds.

    Returns:
        VideoPayload with extracted frames and/or full video data.
    """
    config = config or SecurityConfig()
    is_url = _is_url(source)

    # For local files, validate path
    if not is_url:
        validate_local_path(source, config=config)
        video_path = source
        raw_bytes = None
    else:
        validate_url(source, config=config)
        raw_bytes, final_url, _ = await _load_bytes_from_url(
            source,
            config=config,
            max_redirects=max_redirects,
            timeout=timeout,
        )

    # Determine MIME type
    mime_type = _guess_mime(source) or "video/mp4"

    # Full video encoding (optional, can be very large)
    full_b64: Optional[str] = None
    if encode_full_video:
        if raw_bytes:
            if len(raw_bytes) > config.max_file_size:
                raise FileSizeError(
                    f"Video size {len(raw_bytes):,} bytes exceeds limit "
                    f"of {config.max_file_size:,} bytes."
                )
            full_b64 = base64.b64encode(raw_bytes).decode("ascii")
        else:
            check_file_size(video_path, config=config)
            with open(video_path, "rb") as f:
                full_b64 = base64.b64encode(f.read()).decode("ascii")

    # Frame extraction
    frames: list[VideoFrame] = []
    if num_frames > 0:
        try:
            frames = _extract_frames_opencv(
                source,
                num_frames=num_frames,
                is_url=is_url,
                config=config,
                max_redirects=max_redirects,
                timeout=timeout,
                raw_bytes=raw_bytes,
            )
        except ImportError:
            # OpenCV not installed
            pass
        except VideoError:
            pass

        # Fallback to ffmpeg if OpenCV failed
        if not frames:
            if is_url and raw_bytes:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False
                )
                tmp.write(raw_bytes)
                tmp.close()
                try:
                    frames = _extract_frames_ffmpeg_fallback(
                        tmp.name, num_frames=num_frames
                    )
                finally:
                    os.remove(tmp.name)
            elif not is_url:
                try:
                    frames = _extract_frames_ffmpeg_fallback(
                        video_path, num_frames=num_frames
                    )
                except VideoError:
                    pass

    # Attempt to get video dimensions from first frame or metadata
    width, height = 0, 0
    duration = 0.0
    if frames:
        # Get dimensions from first frame
        import io as _io
        frame_bytes = base64.b64decode(frames[0].data)
        try:
            with Image.open(_io.BytesIO(frame_bytes)) as img:
                width, height = img.size
        except Exception:
            pass
        if frames:
            duration = frames[-1].timestamp_sec

    return VideoPayload(
        data=full_b64,
        mime_type=mime_type,
        source=source,
        duration_sec=duration,
        width=width,
        height=height,
        frames=frames,
        extra={"frame_count": len(frames)},
    )


# ---------------------------------------------------------------------------
# Convenience: load media (auto-detect image vs video)
# ---------------------------------------------------------------------------


async def load_media(
    source: str,
    *,
    config: Optional[SecurityConfig] = None,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    force_downsample: bool = False,
    num_frames: int = DEFAULT_VIDEO_FRAME_COUNT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> ImagePayload | VideoPayload:
    """Load media from a path or URL, auto-detecting image vs video.

    Video extensions trigger video loading; everything else is treated
    as an image.
    """
    config = config or SecurityConfig()
    video_exts = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
    ext = Path(source).suffix.lower()

    if ext in video_exts:
        return await load_video(
            source,
            config=config,
            num_frames=num_frames,
            max_redirects=max_redirects,
            timeout=timeout,
        )
    else:
        return await load_image(
            source,
            config=config,
            max_dimension=max_dimension,
            force_downsample=force_downsample,
            max_redirects=max_redirects,
            timeout=timeout,
        )
