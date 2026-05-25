# Vision MCP Server

**English** | [中文](README.md)

Give your AI coding tools the ability to see and understand images and videos.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## What Is This?

In one sentence: **an independent vision plugin** that connects to your AI coding tools via the [MCP protocol](https://modelcontextprotocol.io/) (Model Context Protocol).

How it works:

```
Your AI editor                      Vision MCP Server               Vision Model API
(Claude Code / Cursor / ...)  →  (this project, runs locally)  →  (OpenAI / Anthropic / Qwen-VL / Ollama)
        ↑                                                                       |
        └───────────────────── returns analysis results ←───────────────────────┘
```

## Who Needs It?

**Case 1: Your AI editor uses a text-only model**

Cursor, Windsurf, Claude Code and similar tools all support sending images in their UI. But whether they can actually understand those images depends on the underlying model. If you've connected a privately deployed open-source model, an internal enterprise API, or any other text-only third-party model, images simply won't work. This plugin solves that — it calls dedicated vision models to process images, completely independent of what model your editor uses.

**Case 2: Your model supports images, but you need more**

Even with a multimodal model underneath, editors typically can't:
- Analyze videos (auto-extract keyframes)
- Do batch OCR (extract text from screenshots)
- Compare multiple images (side-by-side comparison of up to 10 images)
- Switch vision models independently (code with GPT-4o, understand Chinese images with Qwen-VL)
- Keep images private (run vision models locally via Ollama, images never leave your machine)

---

## 3-Minute Setup

### Step 1: Install

Requires Python 3.11 or later. Run `python3 --version` to check.

```bash
git clone https://github.com/xiaoshengwpp/mcp-server-vision.git
cd mcp-server-vision
pip3 install .
```

Verify the installation:

```bash
# Verify the package installed correctly
python3 -c "from vision_mcp import serve; print('✅ Installed successfully')"

# Note this path — you'll need it in Step 3
which python3        # macOS / Linux
where python         # Windows
```

> The command above outputs the full path to Python (e.g. `/opt/homebrew/bin/python3` or `C:\Python311\python.exe`). **Save it — you'll need it for the MCP config in Step 3.**

### Step 2: Pick a Vision Model

You need at least one AI model API that can process images. Choose whichever you prefer:

| Provider | Model | Strengths | Get a Key |
|----------|-------|-----------|-----------|
| **Alibaba DashScope** | Qwen-VL | Best for Chinese, affordable | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| **OpenAI** | GPT-4o | Best all-around | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | Claude 3.5 Sonnet | Excellent detail | [console.anthropic.com](https://console.anthropic.com/) |
| **Ollama** | LLaVA | Runs locally, free, no key | [ollama.com](https://ollama.com/) |

After getting your key, there are two ways to configure it (Option A recommended):

**Option A: Put keys directly in the MCP config (recommended, most reliable)**

No file creation needed — just put your key in the `env` field of the MCP config JSON in Step 3.

**Option B: Create a `.env` file**

Create `.env` in **the working directory where you'll start the server** (for SSE mode, it's wherever you `cd` to in the terminal; for stdio mode, it's your Claude Code project root):

```env
# .env file contents (fill in one or more)
DASHSCOPE_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# If using Ollama locally, no key needed — just the URL:
# OLLAMA_BASE_URL=http://localhost:11434
```

### Step 3: Connect Your AI Editor

Different editors configure differently. Find yours:

<details>
<summary><b>Claude Code</b> (recommended, stdio mode)</summary>

Edit `.mcp.json` in your project root (or `~/.claude.json` for global config):

```json
{
  "mcpServers": {
    "vision": {
      "command": "python3",
      "args": ["-m", "vision_mcp"],
      "env": {
        "OPENAI_API_KEY": "sk-your-key"
      }
    }
  }
}
```

> **Important:** Replace the `"command"` value with the full path from `which python3` in Step 1 (e.g. `"/opt/homebrew/bin/python3"`). This prevents issues when multiple Python versions are installed.

> **stdio mode**: The editor automatically starts and manages the MCP Server process. No manual server startup needed. API keys are passed via the `env` field — no `.env` file required.

</details>

<details>
<summary><b>Cursor</b> (SSE mode)</summary>

**1. Start the MCP Server first (in a terminal — keep it running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python -m vision_mcp
```

You should see `Starting Vision MCP Server (transport=sse)`. **Don't close this terminal window.**

**2. Configure in Cursor:**

Go to `Cursor Settings` → `MCP` → click `+ Add new MCP server`:

- Name: `vision`
- Type: `sse`
- URL: `http://localhost:8000/sse`

</details>

<details>
<summary><b>Windsurf</b> (SSE mode)</summary>

**1. Start the MCP Server (keep terminal running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python -m vision_mcp
```

**2. Configure in Windsurf:**

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "vision": {
      "serverUrl": "http://localhost:8000/sse"
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b> (SSE mode)</summary>

**1. Start the MCP Server (keep terminal running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python -m vision_mcp
```

**2. Edit the config file:**

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vision": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

</details>

<details>
<summary><b>Cherry Studio / Other MCP Clients</b></summary>

Any MCP-compatible client can connect.

- **stdio mode**: set command to the full path from `which python3`, args to `["-m", "vision_mcp"]`
- **SSE mode**: start the server first (`VISION_MCP_TRANSPORT=sse python3 -m vision_mcp`), then connect to `http://localhost:8000/sse`

</details>

### Step 4: Try It Out

Once configured, just mention images in your conversation:

```
What does this error screenshot say? ~/Desktop/error.png
```

```
What UI components are in this design mockup? Generate the React code: ~/Desktop/mockup.png
```

```
Extract all text from this invoice scan: ~/Desktop/invoice.jpg
```

```
Compare these two screenshots — what changed?
- ~/Desktop/v1.png
- ~/Desktop/v2.png
```

> **Note:** Local file paths must be within the `allowed_paths` directories (defaults to `~` and `/tmp`). If a path is rejected, add its directory to `config.yaml`.

---

## Available Tools

After setup, your AI editor gains these 6 tools:

### 🖼️ analyze_image — Single Image Analysis

The most commonly used tool. Give it an image, ask anything about it.

**Example prompts:**
```
What UI components are in this screenshot?
What does this error message mean?
Recreate this page using HTML/CSS
```

**Parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `source` | Image path or URL (required) | `~/Desktop/photo.jpg` or `https://...` |
| `prompt` | Your question (optional) | `Describe this image` |
| `detail` | Precision: `low` / `auto` / `high` (optional) | `high` |
| `provider` | Which model to use (optional) | `openai` |

### 🖼️🖼️ analyze_multiple_images — Multi-Image Comparison

Analyze 2–10 images at once. Great for UI revision comparisons, A/B testing, etc.

**Example prompts:**
```
Compare these two screenshots — what UI changes do you see?
How do the color schemes differ across these three designs?
```

| Parameter | Description | Example |
|-----------|-------------|---------|
| `sources` | 2–10 image paths or URLs (required) | `["~/a.png", "~/b.png"]` |
| `prompt` | Comparison prompt (optional) | `Find the differences` |
| `provider` | Which model (optional) | `openai` |

### 🎬 analyze_video — Video Analysis

Auto-extracts keyframes from a video and analyzes them. Perfect for screen recordings, tutorials, workflow demos.

**Example prompts:**
```
What workflow is demonstrated in this screen recording?
Describe the main content of this video
```

| Parameter | Description | Example |
|-----------|-------------|---------|
| `source` | Video path or URL (required) | `~/Desktop/demo.mp4` |
| `prompt` | Analysis prompt (optional) | `Describe the video` |
| `max_frames` | Max frames to extract: 1–50 (optional, default 10) | `20` |
| `provider` | Which model (optional) | `anthropic` |

### 📝 ocr_image — Text Extraction (OCR)

Extracts all visible text from an image, preserving layout, tables, and lists.

**Example prompts:**
```
Extract all information from this receipt screenshot
What does this scanned document say?
```

| Parameter | Description | Example |
|-----------|-------------|---------|
| `source` | Image path or URL (required) | `~/Desktop/receipt.jpg` |
| `language` | Language hint (optional) | `en` / `zh` / `auto` |
| `provider` | Which model (optional) | `dashscope` |

### ℹ️ get_supported_formats — List Supported Formats

### ℹ️ get_server_status — Check Server Status

---

## Docker Deployment

If you prefer Docker, one command does it all:

```bash
# Build
docker build -t mcp-server-vision .

# Run (SSE mode)
docker run -d -p 8000:8000 \
  -e OPENAI_API_KEY=sk-xxx \
  -e VISION_MCP_TRANSPORT=sse \
  mcp-server-vision
```

Then connect your client to `http://localhost:8000/sse`.

---

## Configuration

For most users, a `.env` file is all you need. Read on for advanced options.

### Three Ways to Configure (highest priority first)

```
Environment variables (export X=Y) > .env file > config.yaml > built-in defaults
```

### Option 1: `.env` File (Simplest)

Create `.env` in the project root:

```env
DASHSCOPE_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
```

### Option 2: `config.yaml` File

Copy the example and customize:

```bash
cp config.yaml.example config.yaml
```

```yaml
# Provider API Keys (fill in at least one)
dashscope_api_key: ${DASHSCOPE_API_KEY}    # or write the key directly
openai_api_key: ${OPENAI_API_KEY}
anthropic_api_key: ${ANTHROPIC_API_KEY}
ollama_base_url: ${OLLAMA_BASE_URL}

# Model selection (optional, has defaults)
dashscope_model: qwen-vl-max
openai_model: gpt-4o
anthropic_model: claude-3-5-sonnet-20241022

# API settings
api_timeout: 120        # timeout in seconds
max_retries: 3          # retry count on failure

# Security limits
max_image_size_mb: 20   # max image size
max_video_size_mb: 2048 # max video size (2GB)
max_image_pixels: 16000000  # max pixel count (~4000×4000)

# Allowed local directories (only files in these dirs can be read)
# Note: creating config.yaml overrides the defaults (~ and /tmp)
# Add directories you commonly use, e.g. ~/Downloads, ~/Projects
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - /tmp

# Transport mode
transport: stdio        # stdio (default) or sse
log_level: INFO         # DEBUG / INFO / WARNING / ERROR
```

Config file auto-discovery (stops at first match):
1. Path from `VISION_MCP_CONFIG` environment variable
2. `config.yaml` in current directory
3. `~/.config/vision_mcp/config.yaml`

### Option 3: Environment Variables

Every setting has a matching environment variable:

| Variable | Description | Default |
|----------|-------------|---------|
| `DASHSCOPE_API_KEY` | DashScope API key | — |
| `OPENAI_API_KEY` | OpenAI key | — |
| `ANTHROPIC_API_KEY` | Anthropic key | — |
| `OLLAMA_BASE_URL` | Ollama URL | — |
| `OLLAMA_MODEL` | Ollama model | `llava:latest` |
| `DASHSCOPE_MODEL` | DashScope model | `qwen-vl-max` |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o` |
| `ANTHROPIC_MODEL` | Anthropic model | `claude-3-5-sonnet-20241022` |
| `MAX_IMAGE_SIZE_MB` | Max image size (MB) | `20` |
| `MAX_VIDEO_SIZE_MB` | Max video size (MB) | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | Max video duration (min) | `120` |
| `VISION_MCP_TRANSPORT` | Transport mode | `stdio` |
| `VISION_MCP_CONFIG` | Config file path | auto-discover |
| `VISION_MCP_LOG_LEVEL` | Log level | `INFO` |

### stdio vs SSE: Which Transport Mode?

| | stdio Mode | SSE Mode |
|---|---|---|
| **Who starts the server** | Editor starts it automatically | You start it manually |
| **Lifecycle** | Stops when editor closes | Independent process, runs continuously |
| **Best for** | Claude Code | Cursor / Windsurf / Claude Desktop |
| **Config format** | `command` + `args` | `url` |

Rule of thumb: **Claude Code → stdio. Everything else → SSE.**

---

## Security

The MCP Server is invoked by AI clients to read files and access URLs, so security is critical.

**Path whitelist** — Only directories listed in `allowed_paths` can be read. Defaults to `~` (home) and `/tmp`. Path resolution follows symlinks; symlink-based escapes are blocked.

**SSRF protection** — Automatically blocks URL requests to internal addresses:
- Loopback (`localhost`, `127.0.0.1`, `::1`)
- Private ranges (`10.x.x.x`, `172.16-31.x.x`, `192.168.x.x`)
- Cloud metadata endpoints (AWS / GCP / Azure / Alibaba Cloud)
- Non-HTTP protocols (`file://`, `ftp://`, etc.)
- HTTP redirects are validated hop-by-hop to prevent redirect-based bypasses

**Resource limits** — File size, pixel count, redirect count, and timeout are all capped to prevent resource exhaustion.

**MIME validation** — Real MIME types are detected via magic bytes in file headers. Extensions are not trusted. Prevents malicious files disguised as images.

---

## Supported Formats

**Images:** JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC, HEIF, AVIF
- Max 20 MB / 16 MP (~4000×4000)
- Auto-downsampled above 4096px

**Videos:** MP4, AVI, MOV, MKV, WebM
- Max 2 GB / 120 minutes
- Frame extraction requires OpenCV (`pip3 install opencv-python`) or ffmpeg

---

## FAQ

**Getting `command not found: python` or `No module named vision_mcp`?**

The Python path doesn't match. Run `which python3` (macOS/Linux) or `where python` (Windows) in your terminal, then put the full path in the MCP config's `command` field. For example:
```json
{
  "command": "/opt/homebrew/bin/python3",
  "args": ["-m", "vision_mcp"]
}
```

**Getting `pip3: command not found`?**

Use `python3 -m pip install .` instead of `pip3 install .`.

**My model already supports images (e.g. GPT-4o). Do I still need this?**

If you only need single-image analysis, maybe not. But if you need video analysis, batch OCR, multi-image comparison, model switching, or local privacy, this plugin provides capabilities your editor doesn't have natively.

**How do I use multiple models at once?**

Just put multiple keys in your `.env`. The first available one becomes the default. You can also specify in conversation: "analyze this image using dashscope".

**Getting "No providers configured" error?**

No API key found. Add at least one key to your `.env` file or set the corresponding environment variable.

**Getting "Path is outside allowed directories" error?**

The image path isn't in the whitelist. Add the image's directory to `allowed_paths` in `config.yaml`.

**Video analysis fails / no frames extracted?**

Install OpenCV or ffmpeg:
```bash
pip3 install opencv-python   # recommended
# or
brew install ffmpeg          # macOS
apt install ffmpeg           # Ubuntu/Debian
```

**SSE mode starts but client can't connect?**

Confirm the server is running (terminal should show `Starting Vision MCP Server`), and check that your firewall allows port 8000.

---

## Project Structure

```
mcp-server-vision/
├── src/vision_mcp/
│   ├── server.py          # MCP server entry point + 6 tool definitions
│   ├── config.py          # Configuration (YAML / .env / env vars)
│   ├── security.py        # Security (path whitelist / SSRF / MIME detection)
│   ├── media.py           # Media loading (image/video, base64, HTTP redirects)
│   ├── __main__.py        # python -m entry point
│   └── providers/         # Vision model adapter layer
│       ├── __init__.py
│       └── base.py        # All provider implementations (OpenAI / Ollama / Anthropic)
├── tests/                 # Test suite (117 tests)
├── config.yaml.example    # Configuration example
├── Dockerfile             # Docker build file
└── pyproject.toml         # Project metadata and dependencies
```

---

## Development

```bash
pip3 install -e ".[dev]"   # install dev dependencies
pytest                     # run tests
pytest --cov=vision_mcp    # tests + coverage
ruff check src/            # lint
mypy src/                  # type check
```

---

## License

[MIT License](LICENSE)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP protocol specification
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP Server framework
- [httpx](https://www.python-httpx.org/) — Async HTTP client
- [Pillow](https://pillow.readthedocs.io/) — Image processing library
- [OpenCV](https://opencv.org/) — Computer vision library
