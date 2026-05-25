# Vision MCP Server

**English** | [中文](README.md)

A production-grade MCP Server that gives AI coding assistants the ability to **see and understand images and videos**.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## Why This Project?

AI coding tools like Cursor, Windsurf, and Claude Code all support image input in their client UI. However, **whether they can actually understand images depends entirely on the underlying model's multimodal capabilities**. With multimodal models like GPT-4o or Claude 3.5 Sonnet, image recognition works out of the box. But when you connect a **custom third-party API model that only supports text** — privately deployed open-source models, internal enterprise APIs, etc. — the client has no way to process images at all.

Even when the underlying model does support images, these tools typically lack:

- **Video analysis** — auto-extract keyframes and analyze video content frame by frame
- **Batch OCR** — extract structured text from multiple document screenshots
- **Multi-image comparison** — compare up to 10 images side by side
- **Independent vision model selection** — e.g., use GPT-4o for coding but Qwen-VL for Chinese image understanding
- **Local privacy** — run vision models locally via Ollama, images never leave your machine

**Vision MCP Server** provides a **vision processing layer that is independent of the client's underlying model** — regardless of what model your AI tool uses, it can call dedicated vision models via the MCP protocol to understand images and videos.

---

## What It Can Do

| Tool | Function | Description |
|------|----------|-------------|
| `analyze_image` | Image Analysis | Analyze a single image from a local file or URL |
| `analyze_multiple_images` | Multi-Image Compare | Compare 2–10 images side-by-side |
| `analyze_video` | Video Analysis | Auto-extract keyframes and analyze video content |
| `ocr_image` | OCR | Extract text from images, multi-language support |
| `get_supported_formats` | Format Info | List supported image and video formats |
| `get_server_status` | Server Status | View current configuration and runtime status |

---

## Quick Start

### 1. Install

```bash
# Option A: Standard install (recommended)
git clone https://github.com/yourusername/vision-mcp.git
cd vision-mcp
pip install .

# Option B: Development mode
pip install -e .
```

### 2. Configure an API Key

Set at least one vision model provider:

```bash
# Pick the provider(s) you use
export DASHSCOPE_API_KEY="sk-xxx"       # Alibaba Cloud DashScope (Qwen-VL)
export OPENAI_API_KEY="sk-xxx"          # OpenAI (GPT-4o)
export ANTHROPIC_API_KEY="sk-ant-xxx"   # Anthropic (Claude 3.5 Sonnet)
export OLLAMA_BASE_URL="http://localhost:11434"  # Ollama local (no key needed)
```

> **Tip:** You can also use a `.env` file in the project root — the server reads it automatically.

### 3. Connect Your MCP Client

#### Claude Code (stdio mode — recommended)

Edit `~/.claude.json` or your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "vision": {
      "command": "python",
      "args": ["-m", "vision_mcp"],
      "env": {
        "OPENAI_API_KEY": "sk-xxx"
      }
    }
  }
}
```

#### Claude Desktop / Cursor / Windsurf (SSE mode)

Start the server first:

```bash
VISION_MCP_TRANSPORT=sse python -m vision_mcp
```

Then configure your client:

```json
{
  "mcpServers": {
    "vision": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### 4. Use It

Once configured, just mention images in your conversation:

```
Analyze this screenshot: /path/to/error-screenshot.png

What UI components are in this design mockup? Generate React code for it:
https://example.com/mockup.png

Extract all text from this document scan: /path/to/invoice.jpg

Compare these two screenshots and find the differences:
- /path/to/before.png
- /path/to/after.png
```

---

## Docker Deployment

```bash
# Build the image
docker build -t vision-mcp .

# Run the container (SSE mode)
docker run -d -p 8000:8000 \
  -e OPENAI_API_KEY=sk-xxx \
  -e VISION_MCP_TRANSPORT=sse \
  vision-mcp
```

Client configuration:

```json
{
  "mcpServers": {
    "vision": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

---

## Tool Reference

### analyze_image — Single Image Analysis

```json
{
  "source": "/path/to/image.jpg",
  "prompt": "Describe this image in detail",
  "detail": "auto",
  "provider": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Image file path or URL |
| `prompt` | string | No | Analysis prompt (default: "Describe in detail") |
| `detail` | string | No | Detail level: `low` / `auto` / `high` |
| `provider` | string | No | Provider name, or default if omitted |

### analyze_multiple_images — Multi-Image Comparison

```json
{
  "sources": ["/path/to/image1.jpg", "/path/to/image2.jpg"],
  "prompt": "Compare these images and describe their differences",
  "provider": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sources` | list | Yes | 2–10 image paths or URLs |
| `prompt` | string | No | Comparison prompt |
| `provider` | string | No | Provider name |

### analyze_video — Video Analysis

```json
{
  "source": "/path/to/video.mp4",
  "prompt": "Describe the main content of this video",
  "max_frames": 10,
  "provider": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Video file path or URL |
| `prompt` | string | No | Analysis prompt |
| `max_frames` | int | No | Max frames to extract (1–50), default 10 |
| `provider` | string | No | Provider name |

### ocr_image — Text Extraction (OCR)

```json
{
  "source": "/path/to/document.jpg",
  "language": "auto",
  "provider": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Image file path or URL |
| `language` | string | No | Language hint: `auto` / `en` / `zh` etc. |
| `provider` | string | No | Provider name |

---

## Configuration

### Priority Order

```
Environment variables > .env file > config.yaml > defaults
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `DASHSCOPE_API_KEY` | DashScope API Key | — |
| `OLLAMA_BASE_URL` | Ollama server URL | — |
| `OLLAMA_MODEL` | Ollama model name | `llava:latest` |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o` |
| `ANTHROPIC_MODEL` | Anthropic model name | `claude-3-5-sonnet-20241022` |
| `DASHSCOPE_MODEL` | DashScope model name | `qwen-vl-max` |
| `MAX_IMAGE_SIZE_MB` | Max image size (MB) | `20` |
| `MAX_VIDEO_SIZE_MB` | Max video size (MB) | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | Max video duration (min) | `120` |
| `VISION_MCP_TRANSPORT` | Transport mode | `stdio` |
| `VISION_MCP_CONFIG` | Config file path | auto-discover |
| `VISION_MCP_LOG_LEVEL` | Log level | `INFO` |

### Config File

Copy `config.yaml.example` to `config.yaml`:

```yaml
# Provider API Keys (at least one required)
openai_api_key: ${OPENAI_API_KEY}
anthropic_api_key: ${ANTHROPIC_API_KEY}
dashscope_api_key: ${DASHSCOPE_API_KEY}
ollama_base_url: ${OLLAMA_BASE_URL}

# Model settings
openai_model: gpt-4o
dashscope_model: qwen-vl-max

# API settings
api_timeout: 120
max_retries: 3

# Security limits
max_image_size_mb: 20
max_video_size_mb: 2048
max_image_pixels: 16000000

# Allowed directories for local file access
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - /tmp

# Transport mode
transport: stdio   # stdio or sse
log_level: INFO
```

Config file auto-discovery (in priority order):
1. Path specified by `VISION_MCP_CONFIG` environment variable
2. `config.yaml` / `config.yml` in the current directory
3. `~/.config/vision_mcp/config.yaml`

---

## Security

As an MCP Server invoked by AI clients to access local files and remote URLs, security is the top priority.

### Path Traversal Protection

Only directories explicitly listed in `allowed_paths` are accessible. Path resolution uses `Path.resolve()` which follows symlinks — symlink-based escapes are caught and blocked.

```yaml
allowed_paths:
  - ~/Desktop      # Only these directories
  - ~/Documents    # are accessible
```

### SSRF Protection

The following URL targets are automatically blocked:

- **Loopback:** `localhost` / `127.0.0.1` / `::1`
- **Private ranges:** `10.0.0.0/8` / `172.16.0.0/12` / `192.168.0.0/16`
- **Cloud metadata:** `169.254.169.254` (AWS/GCP/Azure), `metadata.google.internal`, `100.100.100.200` (Alibaba Cloud)
- **Non-HTTP protocols:** `file://`, `ftp://`, etc.

Redirects are validated hop-by-hop to prevent redirect-based SSRF bypasses.

### Resource Limits

| Limit | Default |
|-------|---------|
| Single file size | 20 MB |
| Video size | 2 GB |
| Image pixel count | 16 MP (4000×4000) |
| HTTP redirects | 5 hops |
| API timeout | 120 seconds |

### MIME Type Validation

Real MIME types are detected via magic bytes in file headers — file extensions are not trusted. Supported image formats: JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC, AVIF.

---

## Supported Formats

### Images

JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC, HEIF, AVIF

- Max size: 20 MB
- Max pixels: 16 MP (~4000×4000)
- Images over 4096px are automatically downsampled

### Videos

MP4, AVI, MOV, MKV, WebM

- Max size: 2 GB
- Max duration: 120 minutes
- Frame extraction requires OpenCV (`pip install opencv-python`) or ffmpeg

---

## Requirements

- **Python** 3.11+
- **ffmpeg** (optional — fallback for video frame extraction)
- **OpenCV** (optional — `pip install opencv-python`, preferred for video frames)

---

## Architecture

```
vision-mcp/
├── src/vision_mcp/
│   ├── server.py          # MCP Server entry point + tool definitions
│   ├── config.py          # Configuration (Pydantic + YAML + env vars)
│   ├── security.py        # Security (path traversal/SSRF/size limits/MIME)
│   ├── media.py           # Media loading (image/video, base64, redirects)
│   ├── __main__.py        # python -m entry point
│   └── providers/         # Provider abstraction layer
│       ├── __init__.py    # Package exports
│       └── base.py        # All provider implementations (OpenAI/Ollama/Anthropic)
├── tests/                 # Test suite (117 tests)
├── config.yaml.example    # Configuration example
├── Dockerfile             # Docker configuration
└── pyproject.toml         # Project metadata
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=vision_mcp

# Lint
ruff check src/

# Type check
mypy src/
```

---

## FAQ

**Which MCP clients are supported?**

Any client that implements the Model Context Protocol: Claude Code, Claude Desktop, Cursor, Windsurf, Cherry Studio, and more.

**Which provider should I use?**

It depends on your use case:
- **OpenAI (GPT-4o)** — Best all-around, native multi-image comparison
- **Anthropic (Claude 3.5 Sonnet)** — Excellent detail and long-context, native multi-image
- **DashScope (Qwen-VL)** — Best Chinese language understanding, affordable
- **Ollama (LLaVA)** — Fully local, no API key needed, privacy-friendly

**Can I use multiple providers at once?**

Yes. Configure multiple API keys and the first one becomes the default. Use the `provider` parameter in tool calls to select a specific provider.

**What do I need for video analysis?**

Install `opencv-python` (recommended) or make sure `ffmpeg` is available:
```bash
pip install opencv-python
# or
brew install ffmpeg   # macOS
apt install ffmpeg    # Ubuntu/Debian
```

**Getting "No providers configured" error?**

You need at least one API key. Set it as an environment variable or in a `.env` file.

---

## License

[MIT License](LICENSE)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) — Standardized protocol for AI tools
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP Server framework
- [httpx](https://www.python-httpx.org/) — Async HTTP client
- [Pillow](https://pillow.readthedocs.io/) — Image processing library
- [OpenCV](https://opencv.org/) — Computer vision library
