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

### Step 2: Configure a Vision Model

You need at least one AI model API that can process images. Choose whichever you prefer:

| Provider | Model | Strengths | Get a Key |
|----------|-------|-----------|-----------|
| **Alibaba DashScope** | Qwen-VL | Best for Chinese, affordable | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| **OpenAI** | GPT-4o | Best all-around | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | Claude 3.5 Sonnet | Excellent detail | [console.anthropic.com](https://console.anthropic.com/) |
| **Ollama** | LLaVA | Runs locally, free, no key | [ollama.com](https://ollama.com/) |
| **vLLM / LM Studio / LocalAI** | Your choice | Self-hosted, no auth, best privacy | Self-deployed |

How to configure depends on your editor:

**If you use Claude Code (stdio mode)** — skip to Step 3. API keys go directly in the MCP config's `env` field. Simplest approach.

**If you use Cursor / Windsurf / Claude Desktop (SSE mode)** — create a `config.yaml` first, then start the server:

```bash
# Create config.yaml in your project directory
cat > config.yaml << 'EOF'
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-your-key
    model: qwen-vl-max
    is_default: true
EOF
```

> **Other provider examples:**
> - OpenAI: `base_url: https://api.openai.com/v1`, `model: gpt-4o`
> - Anthropic: `type: anthropic`, no `base_url` needed, `model: claude-3-5-sonnet-20241022`
> - Local vLLM: `base_url: http://localhost:8000/v1`, `api_key: ""`
> - Ollama: `type: ollama`, `base_url: http://localhost:11434`, `api_key: ""`, `model: llava`
>
> See [Configuration](#configuration) for more examples.

### Step 3: Connect Your AI Editor

Different editors configure differently. Find yours:

<details>
<summary><b>Claude Code</b> (recommended, stdio mode)</summary>

Edit `.mcp.json` in your project root (or `~/.claude.json` for global config):

```json
{
  "mcpServers": {
    "vision": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["-m", "vision_mcp"],
      "env": {
        "VISION_MCP_PROVIDER_TYPE": "openai",
        "VISION_MCP_PROVIDER_BASE_URL": "https://api.openai.com/v1",
        "VISION_MCP_PROVIDER_API_KEY": "sk-your-key",
        "VISION_MCP_PROVIDER_MODEL": "gpt-4o"
      }
    }
  }
}
```

> **Important:** Replace the `"command"` value with the full path from `which python3` in Step 1 (e.g. `"/opt/homebrew/bin/python3"`). This prevents issues when multiple Python versions are installed.

> **stdio mode**: The editor automatically starts and manages the MCP Server process. No manual server startup needed. All configuration is passed via the `env` field — no `config.yaml` required.
>
> **Other provider `env` configurations:**
> - DashScope: change `VISION_MCP_PROVIDER_BASE_URL` to `https://dashscope.aliyuncs.com/compatible-mode/v1`
> - Anthropic: change `VISION_MCP_PROVIDER_TYPE` to `anthropic` (no BASE_URL needed)
> - Local vLLM: change `VISION_MCP_PROVIDER_BASE_URL` to `http://localhost:8000/v1`, leave `VISION_MCP_PROVIDER_API_KEY` empty

</details>

<details>
<summary><b>Cursor</b> (SSE mode)</summary>

**1. Make sure `config.yaml` is created (Step 2), then start the MCP Server (keep terminal running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
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

**1. Make sure `config.yaml` is created (Step 2), then start the MCP Server (keep terminal running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
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

**1. Make sure `config.yaml` is created (Step 2), then start the MCP Server (keep terminal running):**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
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
- **SSE mode**: create `config.yaml` first (Step 2), start the server (`VISION_MCP_TRANSPORT=sse python3 -m vision_mcp`), then connect to `http://localhost:8000/sse`

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

## Checking and Switching Models

### How to check which model is active?

After setup, ask your AI to call the `get_server_status` tool:

```
What vision model am I currently using?
```

The result lists each registered provider and its model name:

```
### Providers
- **dashscope** (OpenAICompatibleProvider): `qwen-vl-max` *(default)*
- **openai** (OpenAICompatibleProvider): `gpt-4o`
```

This means the default model is DashScope's `qwen-vl-max`, with OpenAI's `gpt-4o` also registered.

### How to switch models?

Two ways:

**Option 1: Change config (global)**

Edit the `model` field in your provider's config in `config.yaml`:

```yaml
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-xxx
    model: qwen-vl-plus    # change to your preferred model
    is_default: true
```

Or use environment variables to configure a single provider (overrides config.yaml providers):

```bash
VISION_MCP_PROVIDER_TYPE=openai
VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_MCP_PROVIDER_API_KEY=sk-xxx
VISION_MCP_PROVIDER_MODEL=qwen-vl-plus
```

**Option 2: Per-call override (temporary)**

Every tool has a `model` parameter for one-off model switching:

```
Analyze this image using qwen-vl-plus: ~/Desktop/photo.jpg
```

```
Extract text from this invoice using gpt-4o-mini: ~/Desktop/invoice.jpg
```

The AI will pass the `model` parameter in the tool call automatically — no config changes needed.

### Available DashScope (Bailian) Multimodal Models

If you use Alibaba Cloud DashScope, these models all support image understanding and share the same API key:

| Model ID | Description |
|----------|-------------|
| `qwen-vl-max` | Best vision understanding, complex scenes (default) |
| `qwen-vl-plus` | Great value, sufficient for daily use |
| `qwen2.5-vl-72b-instruct` | 72B parameters, more precise details |
| `qwen2.5-vl-32b-instruct` | 32B parameters, balanced cost/performance |
| `qwen2.5-vl-7b-instruct` | 7B parameters, most affordable |

Switch by editing the `model` field in config.yaml, or passing the `model` parameter per call.

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
| `provider` | Which provider to use (optional) | `openai` |
| `model` | Model override, replaces default (optional) | `gpt-4o-mini` |

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
| `provider` | Which provider (optional) | `openai` |
| `model` | Model override (optional) | `gpt-4o-mini` |

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
| `provider` | Which provider (optional) | `anthropic` |
| `model` | Model override (optional) | `claude-3-haiku-20240307` |

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
| `provider` | Which provider (optional) | `dashscope` |
| `model` | Model override (optional) | `qwen-vl-plus` |

### ℹ️ get_supported_formats — List Supported Formats

### ℹ️ get_server_status — Check Server Status

---

## Docker Deployment

Two commands and you're done:

```bash
# Build
docker build -t mcp-server-vision .

# Run (SSE mode), configure provider via environment variables
docker run -d -p 8000:8000 \
  -e VISION_MCP_TRANSPORT=sse \
  -e VISION_MCP_PROVIDER_TYPE=openai \
  -e VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -e VISION_MCP_PROVIDER_API_KEY=sk-your-key \
  -e VISION_MCP_PROVIDER_MODEL=qwen-vl-max \
  mcp-server-vision
```

Then connect your client to `http://localhost:8000/sse`.

---

## Configuration

If you only need one provider, the `config.yaml` from Step 2 is enough. Read on for advanced usage.

### How Configuration Loading Works

On startup, the server loads configuration in this order:

1. **Load `.env` file** (if present) — injects values into environment variables for YAML `${VAR}` resolution
2. **Load `config.yaml`** (if present) — `${VAR}` references are resolved from env vars and `.env`
3. **Load `VISION_MCP_PROVIDER_*` env vars** (if set) — creates a single provider, **overrides** providers from config.yaml

> In short: `.env` is a helper that provides values for `config.yaml`'s `${VAR}` syntax — it's not a standalone config method. `VISION_MCP_PROVIDER_*` is a shortcut for quickly configuring a single provider.

### Option 1: `config.yaml` (Recommended, Most Flexible)

Copy the example and customize:

```bash
cp config.yaml.example config.yaml
```

**Flexible provider configuration (recommended)**

Use a `providers` list to configure any OpenAI-compatible or Anthropic API:

```yaml
providers:
  # Example 1: Alibaba Cloud DashScope (OpenAI-compatible)
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}  # read from env, or write directly
    model: qwen-vl-plus  # specify any compatible model
    is_default: true

  # Example 2: OpenAI official API
  - name: openai
    type: openai
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o-mini

  # Example 3: Anthropic Claude
  - name: anthropic
    type: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-5-sonnet-20241022
```

**Supports any OpenAI-compatible API**

Any service compatible with OpenAI API can be used directly:

```yaml
providers:
  - name: deepseek
    type: openai
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    is_default: true

  - name: moonshot
    type: openai
    base_url: https://api.moonshot.cn/v1
    api_key: ${MOONSHOT_API_KEY}
    model: moonshot-v1-128k-vision
```

**Supports local Ollama**

```yaml
providers:
  - name: local
    type: ollama
    base_url: http://localhost:11434
    api_key: ""
    model: llava
    is_default: true
```

**Supports locally deployed OpenAI-compatible services (vLLM / LM Studio / LocalAI, etc.)**

These local services typically don't require authentication — leave `api_key` empty:

```yaml
providers:
  - name: local-vllm
    type: openai
    base_url: http://localhost:8000/v1    # vLLM default address
    api_key: ""                            # no key needed for local services
    model: Qwen/Qwen2-VL-7B-Instruct     # your deployed model name
    is_default: true

  # LM Studio example
  # - name: lm-studio
  #   type: openai
  #   base_url: http://localhost:1234/v1
  #   api_key: ""
  #   model: local-model
```

**Other configuration options**

```yaml
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

**Pairing with a `.env` file (recommended)**

If you don't want API keys in plaintext in `config.yaml`, store them in a `.env` file:

```env
# .env (same directory as config.yaml)
DASHSCOPE_API_KEY=sk-your-real-key
OPENAI_API_KEY=sk-your-real-key
```

Reference them in `config.yaml` with `${VAR}`:

```yaml
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}   # auto-loaded from .env
    model: qwen-vl-max
    is_default: true
```

> `.env` is just a helper for `${VAR}` values — it cannot create providers on its own. Must be used with `config.yaml`.

### Option 2: `VISION_MCP_PROVIDER_*` Environment Variables (Quick Single-Provider Setup)

Use `VISION_MCP_PROVIDER_*` environment variables to quickly configure a single provider (overrides providers list in config.yaml):

| Variable | Description | Example |
|----------|-------------|---------|
| `VISION_MCP_PROVIDER_TYPE` | Endpoint type | `openai` / `anthropic` / `ollama` |
| `VISION_MCP_PROVIDER_BASE_URL` | API endpoint URL | `https://api.openai.com/v1` |
| `VISION_MCP_PROVIDER_API_KEY` | API key (can be empty for local services) | `sk-xxx` |
| `VISION_MCP_PROVIDER_MODEL` | Model name | `gpt-4o` |
| `VISION_MCP_PROVIDER_NAME` | Provider name (optional) | `my-provider` |

Other general environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
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

Configure multiple providers in `config.yaml`, each with a different `name`:

```yaml
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-xxx
    model: qwen-vl-max
    is_default: true

  - name: openai
    type: openai
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    model: gpt-4o
```

Then specify in conversation: "analyze this image using openai", or pass `provider: "openai"` in the tool call.

**Getting "No providers configured" error?**

No provider was configured. Check the following:
1. Is there a `config.yaml` in the startup directory (with at least one provider)?
2. Or are `VISION_MCP_PROVIDER_*` environment variables set?
3. Can `${VAR}` references in `config.yaml` be resolved from env vars or `.env`? (Missing values become empty strings, causing the provider to be skipped)

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
├── tests/                 # Test suite (152 tests)
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
