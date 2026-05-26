# Vision MCP Server

**English** | [中文](README.md)

Give your AI coding tools the ability to see and understand images and videos.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## What Is This?

In one sentence: **an independent vision plugin** that connects to your AI editor via the [MCP protocol](https://modelcontextprotocol.io/) (Model Context Protocol).

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
- Switch vision models independently (code with GPT-4o, understand images with Qwen-VL)
- Keep images private (run vision models locally via Ollama, images never leave your machine)

---

## 3-Step Setup

### Step 1: Install

Requires Python 3.11+. Run `python3 --version` to check.

```bash
git clone https://github.com/xiaoshengwpp/mcp-server-vision.git
cd mcp-server-vision
pip3 install .             # If pip3 is not found, use: python3 -m pip install .
```

After installation, note the full Python path (needed for Claude Code stdio mode):

```bash
which python3              # macOS / Linux — remember the full path
where python               # Windows
```

### Step 2: Configure a Vision Model

> **Claude Code users (stdio mode)** can skip this step — configuration is done via `env` fields in Step 3, no config.yaml needed.

Create a `config.yaml` in the **mcp-server-vision directory** (where you ran `pip3 install .`):

```yaml
providers:
  - name: dashscope              # Custom name — pick anything; used to reference this provider in tool calls
    type: openai                 # All OpenAI-compatible APIs use "openai"
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-your-key
    model: qwen-vl-max
    is_default: true             # Set as the default provider

# Extra directories the server can access (~ and /tmp are always allowed; add more here)
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - ~/Downloads
```

> **Note:** config.yaml is loaded from the directory where you start the server. If you start the server from a different directory, place config.yaml there instead.

> **Using a different provider?** Just change `base_url`, `api_key`, and `model`. The `name` can be anything.

| Provider | type | base_url | model example | Get Key |
|----------|------|----------|---------------|---------|
| Alibaba DashScope | `openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max` | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| OpenAI | `openai` | `https://api.openai.com/v1` | `gpt-4o` | [platform.openai.com](https://platform.openai.com/api-keys) |
| DeepSeek | `openai` | `https://api.deepseek.com/v1` | `deepseek-chat` | [platform.deepseek.com](https://platform.deepseek.com/) |
| Anthropic | `anthropic` | Default official; set for third-party proxy | `claude-3-5-sonnet-20241022` | [console.anthropic.com](https://console.anthropic.com/) |
| vLLM / LM Studio / LocalAI | `openai` | Your endpoint (e.g. `http://localhost:8000/v1`) | Your model name | Self-hosted, leave api_key empty |

**Anthropic users** — set `type` to `anthropic`. `base_url` is optional (defaults to official API). Set it for third-party proxy services:

```yaml
providers:
  - name: anthropic
    type: anthropic
    # base_url: https://your-proxy/v1    # Only for third-party proxies; omit for official API
    api_key: sk-ant-your-key
    model: claude-3-5-sonnet-20241022
    is_default: true
```

**Local services** (vLLM / LM Studio / LocalAI) — leave `api_key` empty:

```yaml
providers:
  - name: local
    type: openai
    base_url: http://localhost:8000/v1
    api_key: ""
    model: Qwen/Qwen2-VL-7B-Instruct
    is_default: true
```

> **Don't want plain-text keys?** Create a `.env` file in the same directory and reference values with `${VAR}`:
>
> ```env
> # .env (same directory as config.yaml)
> DASHSCOPE_API_KEY=sk-your-real-key
> ```
>
> ```yaml
> # config.yaml
> providers:
>   - name: dashscope
>     type: openai
>     base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
>     api_key: ${DASHSCOPE_API_KEY}    # auto-loaded from .env
>     model: qwen-vl-max
>     is_default: true
> ```

### Step 3: Connect Your Editor

Choose one based on your editor type:

<details>
<summary><b>Recommended: Cursor / Windsurf / Claude Desktop</b> (SSE mode)</summary>

**1. Make sure config.yaml is created (Step 2), then start the server from the mcp-server-vision directory:**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
```

If you see `Starting Vision MCP Server (transport=sse)`, it's running. **Keep the terminal open.**

**2. Add the MCP server in your editor:**

**Cursor:** Settings → MCP → Add new MCP server → Type: `sse`, URL: `http://localhost:8000/sse`

**Windsurf:** Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "vision": {
      "serverUrl": "http://localhost:8000/sse"
    }
  }
}
```

**Claude Desktop:** Edit the config file (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

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
<summary><b>Claude Code</b> (stdio mode — no manual server startup needed)</summary>

No config.yaml needed — all configuration is done via the `env` fields below. Edit `.mcp.json` in your project root (or global `~/.claude.json`):

```json
{
  "mcpServers": {
    "vision": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["-m", "vision_mcp"],
      "env": {
        "VISION_MCP_PROVIDER_TYPE": "openai",
        "VISION_MCP_PROVIDER_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "VISION_MCP_PROVIDER_API_KEY": "sk-your-key",
        "VISION_MCP_PROVIDER_MODEL": "qwen-vl-max",
        "VISION_MCP_PROVIDER_MAX_TOKENS": "2000"
      }
    }
  }
}
```

> Replace `"command"` with the full path from Step 1 (`which python3`).
>
> For other providers, just change `BASE_URL`, `API_KEY`, and `MODEL`. **Anthropic users** change `PROVIDER_TYPE` to `anthropic`, and either omit `PROVIDER_BASE_URL` (defaults to official API) or set it to a third-party proxy URL.
>
> `VISION_MCP_PROVIDER_MAX_TOKENS` is optional — controls the maximum output length. Set to `4000+` for OCR tasks. Defaults to `2000`.

stdio mode is managed by the editor automatically — no manual startup needed.

</details>

### Try It Out

Once configured, reference images directly in your conversation:

```
What does this error screenshot mean: ~/Desktop/error.png
```

```
Extract all text from this invoice screenshot: ~/Desktop/invoice.jpg
```

```
Compare these two screenshots for differences: ~/Desktop/v1.png and ~/Desktop/v2.png
```

> Local file paths must be within the `allowed_paths` whitelist (defaults: `~` and `/tmp`).

---

## Local Ollama Setup

If you prefer not to use cloud APIs, run vision models locally with Ollama — images never leave your machine.

1. Install Ollama: [ollama.com](https://ollama.com/)
2. Pull a model: `ollama pull llava`
3. Update config.yaml:

```yaml
providers:
  - name: local
    type: ollama
    base_url: http://localhost:11434
    api_key: ""
    model: llava
    is_default: true
```

Startup and editor connection are the same as above.

---

## Switching Models

**Permanent change:** Edit the `model` field in config.yaml, restart the server.

**Per-request override:** Each tool accepts a `model` parameter:

```
Analyze this image using qwen-vl-plus: ~/Desktop/photo.jpg
```

**Available DashScope models** (same API key):

| Model ID | Description |
|----------|-------------|
| `qwen-vl-max` | Best vision understanding, ideal for complex scenes (default) |
| `qwen-vl-plus` | Great value, sufficient for daily use |
| `qwen2.5-vl-72b-instruct` | 72B parameters, more precise details |
| `qwen2.5-vl-32b-instruct` | 32B parameters, balanced performance and cost |

---

## Docker Deployment

```bash
docker build -t mcp-server-vision .
docker run -d -p 8000:8000 \
  -e VISION_MCP_TRANSPORT=sse \
  -e VISION_MCP_PROVIDER_TYPE=openai \
  -e VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -e VISION_MCP_PROVIDER_API_KEY=sk-your-key \
  -e VISION_MCP_PROVIDER_MODEL=qwen-vl-max \
  -e VISION_MCP_PROVIDER_MAX_TOKENS=2000 \
  mcp-server-vision
```

Connect to `http://localhost:8000/sse`.

---

## Available Tools

After configuration, your AI editor gains these tools:

| Tool | Function | Key Parameters |
|------|----------|----------------|
| `analyze_image` | Analyze a single image | `source` (required), `prompt`, `detail`, `model` |
| `analyze_multiple_images` | Compare 2-10 images | `sources` (required), `prompt`, `model` |
| `analyze_video` | Video frame analysis | `source` (required), `prompt`, `max_frames` (1-50), `model` |
| `ocr_image` | Text extraction (OCR) | `source` (required), `language`, `model` |
| `get_server_status` | View current config and models | — |
| `get_supported_formats` | View supported formats | — |

> All analysis tools support a `provider` parameter to specify which provider to use (matching the `name` in config.yaml). Useful when multiple providers are configured.

---

## Security

- **Path whitelist** — Only directories in `allowed_paths` can be read; symlink bypass attacks are blocked
- **SSRF protection** — Auto-blocks internal addresses, cloud metadata endpoints, non-HTTP protocols (only applies to user-supplied image/video URLs; provider API URLs are automatically exempted, so local services like Ollama work without issues)
- **Resource limits** — File size, pixel count, and timeout are all capped
- **MIME validation** — Real type detected via magic bytes, file extensions not trusted

---

## Supported Formats

**Images:** JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC, HEIF, AVIF (max 20MB / 16MP)

**Videos:** MP4, AVI, MOV, MKV, WebM (max 2GB / 120 min; requires `pip3 install opencv-python` or ffmpeg)

---

## FAQ

**Q: Error `command not found: python` or `No module named vision_mcp`?**

Python path mismatch. Run `which python3` and use the full path in your MCP config's `command` field.

**Q: Error "No providers configured"?**

1. Check that `config.yaml` exists with at least one provider
2. Verify `${VAR}` references resolve to actual values (missing vars become empty strings)
3. If using env var mode, check `VISION_MCP_PROVIDER_*` spelling

**Q: Error "Path is outside allowed directories"?**

Home directory (`~`) and `/tmp` are always accessible. If your image is elsewhere (e.g. `/opt/images`), add that directory to `allowed_paths` in config.yaml.

**Q: Video analysis fails / no frames extracted?**

Install OpenCV or ffmpeg: `pip3 install opencv-python` or `brew install ffmpeg`.

**Q: SSE mode starts but client can't connect?**

Confirm the terminal shows `Starting Vision MCP Server`, and check that port 8000 is not blocked by a firewall.

---

## Project Structure

```
mcp-server-vision/
├── src/vision_mcp/
│   ├── server.py          # MCP server entry + tool definitions
│   ├── config.py          # Config management (YAML / .env / env vars)
│   ├── security.py        # Security (path whitelist / SSRF / MIME)
│   ├── media.py           # Media loading (image/video reading)
│   └── providers/         # Vision model adapters (OpenAI / Anthropic / Ollama)
├── tests/                 # Test suite
├── config.yaml.example    # Example config file
├── Dockerfile
└── pyproject.toml
```

---

## Contributing

```bash
pip3 install -e ".[dev]"
pytest                     # Run tests
ruff check src/            # Lint
mypy src/                  # Type check
```

---

## License

[MIT License](LICENSE)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP specification
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP Server framework
- [httpx](https://www.python-httpx.org/) — Async HTTP client
- [Pillow](https://pillow.readthedocs.io/) — Image processing library
- [OpenCV](https://opencv.org/) — Computer vision library
