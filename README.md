# Vision MCP Server

[English](README_EN.md) | **中文**

为 AI 编程助手提供视觉理解能力的 MCP Server —— 让 Claude Code、Cursor、Windsurf 等工具能够"看懂"图片和视频。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## 为什么需要这个项目？

Cursor、Windsurf、Claude Code 等 AI 编程工具的客户端都具备图片输入能力，但**能否理解图片取决于底层模型是否支持多模态**。使用 GPT-4o、Claude 3.5 Sonnet 等多模态模型时，图片理解开箱即用。但很多开发者的实际场景是：

- **使用了只支持文本的自定义第三方模型** — 私有化部署的开源模型、企业内部 API、成本更低的专用模型等，这些模型不具备多模态能力，客户端接入后无法处理图片
- **需要视频分析** — 即使底层模型支持图片，也没有客户端能自动提取视频关键帧并分析
- **需要批量 OCR 或多图对比** — 从文档截图提取文字、对比 UI 截图差异，这些是独立于模型视觉能力之外的功能需求
- **想用不同的模型处理视觉任务** — 比如编程用 GPT-4o，但图片理解想切换到通义千问VL（中文场景更强）
- **本地隐私需求** — 通过 Ollama 在本机运行视觉模型，图片不离开你的电脑

**Vision MCP Server** 解决的核心问题是：提供一个**与客户端底层模型解耦的独立视觉处理层**。无论你的 AI 工具接的是什么模型、那个模型是否支持图片，都可以通过 MCP 协议调用专门的视觉模型来理解图片和视频。

---

## 核心能力

| 工具 | 功能 | 说明 |
|------|------|------|
| `analyze_image` | 图片分析 | 分析单张图片，支持本地文件和 URL |
| `analyze_multiple_images` | 多图对比 | 同时分析 2-10 张图片，发现差异 |
| `analyze_video` | 视频分析 | 自动提取关键帧并分析视频内容 |
| `ocr_image` | 文字识别 | 从图片中提取文字，支持多语言 |
| `get_supported_formats` | 格式查询 | 查看支持的图片和视频格式 |
| `get_server_status` | 状态查询 | 查看当前服务配置和运行状态 |

---

## 快速开始

### 1. 安装

```bash
# 方式 A：pip 安装（推荐）
git clone https://github.com/xiaoshengwpp/mcp-server-vision.git
cd mcp-server-vision
pip install .

# 方式 B：开发模式安装
pip install -e .
```

### 2. 配置 API Key

至少配置一个视觉模型提供商的 API Key：

```bash
# 选择你常用的提供商（任选其一或多个）
export DASHSCOPE_API_KEY="sk-xxx"       # 阿里云 DashScope (通义千问VL)
export OPENAI_API_KEY="sk-xxx"          # OpenAI (GPT-4o)
export ANTHROPIC_API_KEY="sk-ant-xxx"   # Anthropic (Claude 3.5 Sonnet)
export OLLAMA_BASE_URL="http://localhost:11434"  # Ollama 本地部署（无需Key）
```

> **提示：** 也可以使用 `.env` 文件管理密钥，项目会自动读取项目根目录下的 `.env` 文件。

### 3. 配置 MCP 客户端

#### Claude Code（推荐 stdio 模式）

编辑 `~/.claude.json` 或项目的 `.mcp.json`：

```json
{
  "mcpServers": {
    "vision": {
      "command": "python",
      "args": ["-m", "vision_mcp"],
      "env": {
        "DASHSCOPE_API_KEY": "sk-xxx"
      }
    }
  }
}
```

#### Claude Desktop / Cursor / Windsurf（SSE 模式）

先启动服务：

```bash
VISION_MCP_TRANSPORT=sse python -m vision_mcp
```

然后在客户端中配置：

```json
{
  "mcpServers": {
    "vision": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### 4. 开始使用

配置完成后，直接在对话中提及图片即可：

```
请分析这张图片：/path/to/screenshot.png

这张设计稿里有哪些 UI 组件？请帮我生成对应的 React 代码：https://example.com/design.png

提取这张截图中的所有文字：/path/to/document-scan.jpg

帮我对比这两张截图有什么不同：
- /path/to/before.png
- /path/to/after.png
```

---

## Docker 部署

```bash
# 构建镜像
docker build -t vision-mcp .

# 运行容器（SSE 模式）
docker run -d -p 8000:8000 \
  -e DASHSCOPE_API_KEY=sk-xxx \
  -e VISION_MCP_TRANSPORT=sse \
  vision-mcp
```

客户端配置：

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

## 工具详细参数

### analyze_image — 图片分析

```json
{
  "source": "/path/to/image.jpg",
  "prompt": "详细描述这张图片的内容",
  "detail": "auto",
  "provider": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 图片路径或 URL |
| `prompt` | string | 否 | 分析提示词，默认"详细描述" |
| `detail` | string | 否 | 精度级别：`low` / `auto` / `high` |
| `provider` | string | 否 | 指定提供商，不填则使用默认 |

### analyze_multiple_images — 多图对比

```json
{
  "sources": ["/path/to/image1.jpg", "/path/to/image2.jpg"],
  "prompt": "对比这两张图片，找出它们的差异",
  "provider": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sources` | list | 是 | 2-10 张图片路径或 URL |
| `prompt` | string | 否 | 对比提示词 |
| `provider` | string | 否 | 指定提供商 |

### analyze_video — 视频分析

```json
{
  "source": "/path/to/video.mp4",
  "prompt": "描述视频中的主要内容",
  "max_frames": 10,
  "provider": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 视频路径或 URL |
| `prompt` | string | 否 | 分析提示词 |
| `max_frames` | int | 否 | 最多提取帧数（1-50），默认 10 |
| `provider` | string | 否 | 指定提供商 |

### ocr_image — 文字识别

```json
{
  "source": "/path/to/document.jpg",
  "language": "auto",
  "provider": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 图片路径或 URL |
| `language` | string | 否 | 语言提示：`auto` / `zh` / `en` 等 |
| `provider` | string | 否 | 指定提供商 |

---

## 配置参考

### 配置优先级

```
环境变量 > .env 文件 > config.yaml > 默认值
```

### 环境变量一览

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key | - |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `ANTHROPIC_API_KEY` | Anthropic API Key | - |
| `OLLAMA_BASE_URL` | Ollama 服务地址 | - |
| `OLLAMA_MODEL` | Ollama 模型名称 | `llava:latest` |
| `DASHSCOPE_MODEL` | DashScope 模型名称 | `qwen-vl-max` |
| `OPENAI_MODEL` | OpenAI 模型名称 | `gpt-4o` |
| `ANTHROPIC_MODEL` | Anthropic 模型名称 | `claude-3-5-sonnet-20241022` |
| `MAX_IMAGE_SIZE_MB` | 最大图片大小 (MB) | `20` |
| `MAX_VIDEO_SIZE_MB` | 最大视频大小 (MB) | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | 最大视频时长 (分钟) | `120` |
| `VISION_MCP_TRANSPORT` | 传输模式 | `stdio` |
| `VISION_MCP_CONFIG` | 配置文件路径 | 自动发现 |
| `VISION_MCP_LOG_LEVEL` | 日志级别 | `INFO` |

### 配置文件

复制 `config.yaml.example` 为 `config.yaml`：

```yaml
# 提供商 API Keys（至少配置一个）
dashscope_api_key: ${DASHSCOPE_API_KEY}
openai_api_key: ${OPENAI_API_KEY}
anthropic_api_key: ${ANTHROPIC_API_KEY}
ollama_base_url: ${OLLAMA_BASE_URL}

# 模型配置
dashscope_model: qwen-vl-max
openai_model: gpt-4o

# API 设置
api_timeout: 120
max_retries: 3

# 安全限制
max_image_size_mb: 20
max_video_size_mb: 2048
max_image_pixels: 16000000

# 允许访问的目录
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - /tmp

# 传输模式
transport: stdio   # stdio 或 sse
log_level: INFO
```

配置文件自动发现路径（按优先级）：
1. `VISION_MCP_CONFIG` 环境变量指定的路径
2. 当前目录下的 `config.yaml` / `config.yml`
3. `~/.config/vision_mcp/config.yaml`

---

## 安全机制

作为 MCP Server，本工具会被 AI 客户端调用来读取本地文件和远程 URL。安全是第一优先级。

### 路径遍历防护

只允许访问 `allowed_paths` 中明确列出的目录。路径解析使用 `Path.resolve()` 跟随符号链接，防止通过 symlink 绕过限制。

```yaml
allowed_paths:
  - ~/Desktop      # 只允许访问桌面
  - ~/Documents    # 和文档目录
```

### SSRF 防护

自动阻止 URL 请求访问以下地址：

- 环回地址：`localhost` / `127.0.0.1` / `::1`
- 私有网段：`10.0.0.0/8` / `172.16.0.0/12` / `192.168.0.0/16`
- 云服务元数据：`169.254.169.254`（AWS/GCP/Azure）、`metadata.google.internal`、`100.100.100.200`（阿里云）
- 非 HTTP 协议：`file://`、`ftp://` 等

重定向逐跳验证，防止通过重定向跳转到内网。

### 资源限制

| 限制项 | 默认值 |
|--------|--------|
| 单文件大小 | 20 MB |
| 视频大小 | 2 GB |
| 图片像素数 | 16 MP (4000x4000) |
| HTTP 重定向 | 5 次 |
| API 超时 | 120 秒 |

### MIME 类型验证

基于文件头魔术字节检测真实 MIME 类型，不信任文件扩展名。支持的图片格式：JPEG、PNG、GIF、WebP、BMP、TIFF、HEIC、AVIF。

---

## 支持的格式

### 图片

JPEG、PNG、GIF、WebP、BMP、TIFF、HEIC、HEIF、AVIF

- 最大尺寸：20 MB
- 最大像素：16 MP（约 4000×4000）
- 超过 4096px 的图片自动降采样

### 视频

MP4、AVI、MOV、MKV、WebM

- 最大尺寸：2 GB
- 最大时长：120 分钟
- 帧提取需要 OpenCV (`pip install opencv-python`) 或 ffmpeg

---

## 系统要求

- **Python** 3.11+
- **ffmpeg**（可选，视频帧提取的备选方案）
- **OpenCV**（可选，`pip install opencv-python`，视频帧提取的首选方案）

---

## 架构

```
vision-mcp/
├── src/vision_mcp/
│   ├── server.py          # MCP Server 主程序 + 工具定义
│   ├── config.py          # 配置管理 (Pydantic + YAML + 环境变量)
│   ├── security.py        # 安全模块 (路径遍历/SSRF/文件大小/MIME)
│   ├── media.py           # 媒体加载 (图片/视频, base64编码, 重定向跟踪)
│   ├── __main__.py        # python -m 入口
│   └── providers/         # Provider 抽象层
│       ├── __init__.py    # 包导出
│       └── base.py        # 所有 Provider 实现 (OpenAI/Ollama/Anthropic)
├── tests/                 # 测试用例 (117 个)
├── config.yaml.example    # 配置示例
├── Dockerfile             # Docker 配置
└── pyproject.toml         # 项目配置
```

---

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 带覆盖率
pytest --cov=vision_mcp

# 代码检查
ruff check src/

# 类型检查
mypy src/
```

---

## 常见问题

**Q: 支持哪些 MCP 客户端？**

任何支持 Model Context Protocol 的客户端都可以使用，包括 Claude Code、Claude Desktop、Cursor、Windsurf、Cherry Studio 等。

**Q: 哪个 Provider 最好用？**

取决于你的需求：
- **DashScope（通义千问VL）**：中文理解能力最强，国内访问快，价格便宜
- **OpenAI (GPT-4o)**：综合能力最强，支持多图对比
- **Anthropic (Claude 3.5 Sonnet)**：长文本和细节描述出色，支持多图对比
- **Ollama (LLaVA)**：完全本地运行，无需 API Key，适合隐私敏感场景

**Q: 如何同时使用多个 Provider？**

配置多个 API Key 即可。第一个配置的 Provider 会成为默认，你可以通过工具参数中的 `provider` 字段指定使用特定 Provider。

**Q: 视频分析需要什么额外依赖？**

安装 `opencv-python`（推荐）或确保系统已安装 `ffmpeg`：
```bash
pip install opencv-python
# 或
brew install ffmpeg   # macOS
apt install ffmpeg    # Ubuntu/Debian
```

**Q: 报错 "No providers configured"？**

至少需要配置一个 API Key。设置环境变量或在 `.env` 文件中配置。

---

## 许可证

[MIT License](LICENSE)

---

## 致谢

- [Model Context Protocol](https://modelcontextprotocol.io/) — AI 工具标准化协议
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP Server 框架
- [httpx](https://www.python-httpx.org/) — 异步 HTTP 客户端
- [Pillow](https://pillow.readthedocs.io/) — 图像处理库
- [OpenCV](https://opencv.org/) — 计算机视觉库
