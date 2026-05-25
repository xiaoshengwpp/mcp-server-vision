# Vision MCP Server

[English](README_EN.md) | **中文**

让你的 AI 编程工具能够「看懂」图片和视频。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## 它是什么？

一句话：**一个独立的视觉处理插件**，通过 [MCP 协议](https://modelcontextprotocol.io/)（Model Context Protocol）接入你的 AI 编程工具。

工作原理很简单：

```
你的 AI 编辑器                    Vision MCP Server              视觉模型 API
(Claude Code / Cursor / ...)  →  (本项目，运行在你的电脑上)  →  (OpenAI / Anthropic / 通义千问VL / Ollama)
        ↑                                                              |
        └──────────────────── 返回分析结果 ←─────────────────────────────┘
```

## 谁需要它？

**场景一：你的 AI 编辑器用的是不支持图片的模型**

Cursor、Windsurf、Claude Code 等工具的客户端都支持发送图片，但能不能理解图片取决于底层模型。如果你接的是私有化部署的开源模型、企业内部 API、或其他只支持文本的第三方模型，那图片发过去就是白搭。这个插件帮你解决——它调用独立的视觉模型来处理图片，跟你的编辑器用什么模型无关。

**场景二：你的模型支持图片，但需要更强的视觉能力**

即使底层模型能看图，编辑器本身通常也做不到：
- 分析视频（自动提取关键帧）
- 批量 OCR（从截图提取文字）
- 多图对比（同时对比最多 10 张图片）
- 切换视觉模型（编程用 GPT-4o，图片理解用通义千问VL）
- 本地隐私（通过 Ollama 在本机跑视觉模型，图片不离开你的电脑）

---

## 3 分钟上手

### 第一步：安装

需要 Python 3.11 或更高版本。终端输入 `python3 --version` 确认版本。

```bash
git clone https://github.com/xiaoshengwpp/mcp-server-vision.git
cd mcp-server-vision
pip3 install .
```

安装完成后，验证一下：

```bash
# 验证包是否安装成功
python3 -c "from vision_mcp import serve; print('✅ 安装成功')"

# 记住这个路径，第三步要用
which python3        # macOS / Linux
where python         # Windows
```

> 上面的命令会输出 Python 的完整路径（例如 `/opt/homebrew/bin/python3` 或 `/usr/local/bin/python3`），**记下来，第三步配置 MCP 时需要用到**。

### 第二步：配置视觉模型

你需要至少一个能处理图片的 AI 模型 API。选你顺手的那个：

| 提供商 | 模型 | 特点 | 获取 Key |
|--------|------|------|----------|
| **阿里云 DashScope** | 通义千问VL | 中文最强，国内快，便宜 | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| **OpenAI** | GPT-4o | 综合能力最强 | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | Claude 3.5 Sonnet | 细节描述出色 | [console.anthropic.com](https://console.anthropic.com/) |
| **Ollama** | LLaVA | 本地运行，免费，无需 Key | [ollama.com](https://ollama.com/) |
| **vLLM / LM Studio / LocalAI** | 自选 | 本地部署，免鉴权，隐私最佳 | 自行部署 |

配置方式取决于你用的编辑器类型：

**如果你用 Claude Code（stdio 模式）** — 跳到第三步，API Key 直接写在 MCP 配置的 `env` 字段里，最简单。

**如果你用 Cursor / Windsurf / Claude Desktop（SSE 模式）** — 需要先配置 provider，再启动服务。推荐在项目目录创建 `config.yaml`：

```bash
# 在项目目录创建 config.yaml
cat > config.yaml << 'EOF'
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-你的key
    model: qwen-vl-max
    is_default: true
EOF
```

> **其他 provider 示例：**
> - OpenAI：`base_url: https://api.openai.com/v1`，`model: gpt-4o`
> - Anthropic：`type: anthropic`，不需要 `base_url`，`model: claude-3-5-sonnet-20241022`
> - 本地 vLLM：`base_url: http://localhost:8000/v1`，`api_key: ""`
> - Ollama：`type: ollama`，`base_url: http://localhost:11434`，`api_key: ""`，`model: llava`
>
> 更多示例见 [配置详解](#配置详解) 部分。

### 第三步：接入你的 AI 编辑器

不同编辑器的配置方式不同，找到你用那个：

<details>
<summary><b>Claude Code</b>（推荐，stdio 模式）</summary>

编辑项目根目录下的 `.mcp.json`（或全局 `~/.claude.json`），添加：

```json
{
  "mcpServers": {
    "vision": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["-m", "vision_mcp"],
      "env": {
        "VISION_MCP_PROVIDER_TYPE": "openai",
        "VISION_MCP_PROVIDER_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "VISION_MCP_PROVIDER_API_KEY": "sk-你的key",
        "VISION_MCP_PROVIDER_MODEL": "qwen-vl-max"
      }
    }
  }
}
```

> **重要：** 把 `"command"` 的值替换为第一步中 `which python3` 输出的完整路径（例如 `"/opt/homebrew/bin/python3"`）。这样即使系统有多个 Python 版本也不会出错。

> **stdio 模式**：编辑器自动启动和管理 MCP Server 进程，不需要手动开服务。最简单的方式。所有配置通过 `env` 字段传入，不需要创建 `config.yaml`。
>
> **其他提供商的 `env` 配置：**
> - OpenAI：`VISION_MCP_PROVIDER_BASE_URL` 改为 `https://api.openai.com/v1`
> - Anthropic：`VISION_MCP_PROVIDER_TYPE` 改为 `anthropic`（不需要 BASE_URL）
> - 本地 vLLM：`VISION_MCP_PROVIDER_BASE_URL` 改为 `http://localhost:8000/v1`，`VISION_MCP_PROVIDER_API_KEY` 留空

</details>

<details>
<summary><b>Cursor</b>（SSE 模式）</summary>

**1. 先确保第二步中已创建 `config.yaml`，然后启动 MCP Server（终端保持运行）：**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
```

看到 `Starting Vision MCP Server (transport=sse)` 就说明启动成功了。**这个终端窗口不要关。**

**2. 在 Cursor 中配置：**

打开 `Cursor Settings` → `MCP` → 点击 `+ Add new MCP server`：

- Name: `vision`
- Type: `sse`
- URL: `http://localhost:8000/sse`

</details>

<details>
<summary><b>Windsurf</b>（SSE 模式）</summary>

**1. 先确保第二步中已创建 `config.yaml`，然后启动 MCP Server（终端保持运行）：**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
```

**2. 在 Windsurf 中配置：**

编辑 `~/.codeium/windsurf/mcp_config.json`：

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
<summary><b>Claude Desktop</b>（SSE 模式）</summary>

**1. 先确保第二步中已创建 `config.yaml`，然后启动 MCP Server（终端保持运行）：**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
```

**2. 编辑配置文件：**

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
<summary><b>Cherry Studio / 其他 MCP 客户端</b></summary>

任何支持 MCP 协议的客户端都可以接入。

- **stdio 模式**：command 填第一步 `which python3` 得到的完整路径，args 填 `["-m", "vision_mcp"]`
- **SSE 模式**：先创建 `config.yaml`（见第二步），启动服务（`VISION_MCP_TRANSPORT=sse python3 -m vision_mcp`），然后连接 `http://localhost:8000/sse`

</details>

### 第四步：试试看

配置完成后，在对话中直接提及图片：

```
帮我看看这个报错截图是什么意思：~/Desktop/error.png
```

```
这张设计稿里有哪些 UI 组件？帮我生成对应的 React 代码：~/Desktop/mockup.png
```

```
提取这张发票截图中的所有文字：~/Desktop/invoice.jpg
```

```
帮我对比这两张截图有什么不同：
- ~/Desktop/v1.png
- ~/Desktop/v2.png
```

> **注意**：本地图片路径必须在 `allowed_paths` 配置范围内（默认允许 `~` 和 `/tmp`）。如果路径被拒绝，在 `config.yaml` 中添加对应目录。

---

## 确认和切换模型

### 如何确认当前使用的是哪个模型？

配置完成后，在对话中让 AI 调用 `get_server_status` 工具：

```
请告诉我当前视觉服务使用的是哪个模型？
```

返回结果会清楚列出每个已注册的提供商及其模型名称，例如：

```
### Providers
- **dashscope** (OpenAICompatibleProvider): `qwen-vl-max` *(default)*
- **openai** (OpenAICompatibleProvider): `gpt-4o`
```

这表示当前默认使用 DashScope 的 `qwen-vl-max` 模型，同时还注册了 OpenAI 的 `gpt-4o`。

### 如何切换模型？

有两种方式：

**方式一：改配置（全局生效）**

在 `config.yaml` 中修改 provider 的 `model` 字段：

```yaml
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-xxx
    model: qwen-vl-plus    # 改成你想用的模型
    is_default: true
```

或通过环境变量配置单个 provider（会覆盖 config.yaml 中的 providers）：

```bash
VISION_MCP_PROVIDER_TYPE=openai
VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_MCP_PROVIDER_API_KEY=sk-xxx
VISION_MCP_PROVIDER_MODEL=qwen-vl-plus
```

**方式二：单次调用指定（临时切换）**

每个工具都有 `model` 参数，可以在单次调用时临时指定模型：

```
用 qwen-vl-plus 模型分析这张图片：~/Desktop/photo.jpg
```

```
用 gpt-4o-mini 识别这张发票里的文字：~/Desktop/invoice.jpg
```

AI 会在调用工具时自动传入 `model` 参数，无需改任何配置文件。

### 百炼平台可用的多模态模型

如果你使用阿里云百炼（DashScope），以下是支持图片理解的模型（共用同一个 API Key）：

| 模型 ID | 说明 |
|---------|------|
| `qwen-vl-max` | 最强视觉理解，复杂场景首选（默认） |
| `qwen-vl-plus` | 性价比高，日常分析够用 |
| `qwen2.5-vl-72b-instruct` | 72B 参数大模型，细节更精准 |
| `qwen2.5-vl-32b-instruct` | 32B 参数，平衡性能和成本 |
| `qwen2.5-vl-7b-instruct` | 7B 参数，最便宜 |

切换只需改 config.yaml 中对应 provider 的 `model` 字段，或在调用时指定 `model` 参数。

配置成功后，你的 AI 编辑器会多出以下 6 个工具：

### 🖼️ analyze_image — 分析单张图片

最常用的工具。给一张图，问任何关于它的问题。

**你可以这样问：**
```
这张截图里有什么 UI 组件？
这个报错信息是什么意思？
帮我用 HTML/CSS 还原这个页面
```

**参数：**

| 参数 | 说明 | 示例 |
|------|------|------|
| `source` | 图片路径或 URL（必填） | `~/Desktop/photo.jpg` 或 `https://...` |
| `prompt` | 你想问什么（可选） | `描述这张图片` |
| `detail` | 精度：`low` / `auto` / `high`（可选） | `high` |
| `provider` | 用哪个提供商（可选） | `dashscope` |
| `model` | 用哪个模型，覆盖默认模型（可选） | `qwen-vl-plus` |

### 🖼️🖼️ analyze_multiple_images — 多图对比

同时分析 2-10 张图片，发现差异。适合 UI 改版对比、A/B 测试分析等。

**你可以这样问：**
```
对比这两张截图，有哪些 UI 变化？
这三张设计稿的配色方案有什么区别？
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `sources` | 2-10 张图片路径或 URL（必填） | `["~/a.png", "~/b.png"]` |
| `prompt` | 对比提示词（可选） | `找出差异` |
| `provider` | 用哪个提供商（可选） | `openai` |
| `model` | 用哪个模型（可选） | `gpt-4o-mini` |

### 🎬 analyze_video — 视频分析

自动从视频中提取关键帧，逐帧分析。适合理解录屏、教程、操作流程等。

**你可以这样问：**
```
这个录屏视频里演示了什么操作流程？
描述这个视频的主要内容
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `source` | 视频路径或 URL（必填） | `~/Desktop/demo.mp4` |
| `prompt` | 分析提示词（可选） | `描述视频内容` |
| `max_frames` | 最多提取几帧：1-50（可选，默认 10） | `20` |
| `provider` | 用哪个提供商（可选） | `anthropic` |
| `model` | 用哪个模型（可选） | `claude-3-haiku-20240307` |

### 📝 ocr_image — 文字识别 (OCR)

从图片中提取所有可见文字，保留排版结构，支持表格和列表。

**你可以这样问：**
```
提取这张发票截图里的所有信息
这张文档扫描件里写了什么？
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `source` | 图片路径或 URL（必填） | `~/Desktop/receipt.jpg` |
| `language` | 语言提示（可选） | `zh`（中文）/ `en` / `auto` |
| `provider` | 用哪个提供商（可选） | `dashscope` |
| `model` | 用哪个模型（可选） | `qwen-vl-plus` |

### ℹ️ get_supported_formats — 查看支持的格式

### ℹ️ get_server_status — 查看服务状态

---

## Docker 部署

如果你更习惯 Docker，两条命令搞定：

```bash
# 构建
docker build -t mcp-server-vision .

# 运行（SSE 模式），通过环境变量配置 provider
docker run -d -p 8000:8000 \
  -e VISION_MCP_TRANSPORT=sse \
  -e VISION_MCP_PROVIDER_TYPE=openai \
  -e VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -e VISION_MCP_PROVIDER_API_KEY=sk-你的key \
  -e VISION_MCP_PROVIDER_MODEL=qwen-vl-max \
  mcp-server-vision
```

然后在客户端中连接 `http://localhost:8000/sse` 即可。

---

## 配置详解

如果你只需要一个 provider，第二步的 `config.yaml` 已经够了。往下看了解更多高级用法。

### 配置加载机制

服务启动时按以下顺序加载配置：

1. **加载 `.env` 文件**（如果存在）— 将其中的值注入到环境变量，供后续 YAML 的 `${VAR}` 引用
2. **加载 `config.yaml`**（如果存在）— 其中 `${VAR}` 会从环境变量和 `.env` 中解析
3. **加载 `VISION_MCP_PROVIDER_*` 环境变量**（如果设置）— 创建单个 provider，**覆盖** config.yaml 中的 providers 列表

> 简单说：`.env` 是给 `config.yaml` 的 `${VAR}` 提供值的辅助工具，不是独立的配置方式。`VISION_MCP_PROVIDER_*` 是快速配置单个 provider 的快捷方式。

### 方式一：`config.yaml`（推荐，最灵活）

复制示例文件并按需修改：

```bash
cp config.yaml.example config.yaml
```

**使用 providers 列表配置（推荐）**

支持任意 OpenAI 兼容或 Anthropic API：

```yaml
providers:
  # 示例 1: 阿里云百炼 DashScope（OpenAI 兼容）
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}  # 从环境变量读取，或直接填写
    model: qwen-vl-plus  # 可以指定任何兼容的模型
    is_default: true

  # 示例 2: OpenAI 官方 API
  - name: openai
    type: openai
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o-mini

  # 示例 3: Anthropic Claude
  - name: anthropic
    type: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-5-sonnet-20241022
```

**支持任意 OpenAI 兼容 API**

任何兼容 OpenAI API 的服务都可以直接使用：

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

**支持本地 Ollama**

```yaml
providers:
  - name: local
    type: ollama
    base_url: http://localhost:11434
    api_key: ""
    model: llava
    is_default: true
```

**支持本地部署的 OpenAI 兼容服务（vLLM / LM Studio / LocalAI 等）**

这类本地服务通常不需要鉴权，`api_key` 留空即可：

```yaml
providers:
  - name: local-vllm
    type: openai
    base_url: http://localhost:8000/v1    # vLLM 默认地址
    api_key: ""                            # 本地服务无需 Key
    model: Qwen/Qwen2-VL-7B-Instruct     # 你部署的模型名
    is_default: true

  # LM Studio 示例
  # - name: lm-studio
  #   type: openai
  #   base_url: http://localhost:1234/v1
  #   api_key: ""
  #   model: local-model
```

**其他配置项**

```yaml
# API 调用设置
api_timeout: 120        # 超时时间（秒）
max_retries: 3          # 失败重试次数

# 安全相关
max_image_size_mb: 20   # 图片大小上限
max_video_size_mb: 2048 # 视频大小上限（2GB）
max_image_pixels: 16000000  # 像素上限（约 4000×4000）

# 允许访问的本地目录（只有这些目录下的文件能被读取）
# 注意：如果你创建了 config.yaml，默认的 ~ 和 /tmp 会被这里的值覆盖
# 建议加上你常用的目录，例如 ~/Downloads、~/Projects 等
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - /tmp

# 服务传输模式
transport: stdio        # stdio（默认）或 sse
log_level: INFO         # DEBUG / INFO / WARNING / ERROR
```

配置文件会在以下位置自动查找（找到第一个就停）：
1. 环境变量 `VISION_MCP_CONFIG` 指定的路径
2. 当前目录下的 `config.yaml`
3. `~/.config/vision_mcp/config.yaml`

**搭配 `.env` 文件使用（推荐）**

如果不想把 API Key 明文写在 `config.yaml` 里，可以用 `.env` 文件存放密钥：

```env
# .env（和 config.yaml 放在同一目录）
DASHSCOPE_API_KEY=sk-你的真实key
OPENAI_API_KEY=sk-你的真实key
```

`config.yaml` 中用 `${VAR}` 引用：

```yaml
providers:
  - name: dashscope
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}   # 自动从 .env 读取
    model: qwen-vl-max
    is_default: true
```

> `.env` 文件只是给 `${VAR}` 提供值的辅助工具，不能单独创建 provider。必须配合 `config.yaml` 使用。

### 方式二：`VISION_MCP_PROVIDER_*` 环境变量（快速配置单个 provider）

通过以下环境变量可以快速配置单个 provider（会覆盖 config.yaml 中的 providers 列表）：

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `VISION_MCP_PROVIDER_TYPE` | 端点类型 | `openai` / `anthropic` / `ollama` |
| `VISION_MCP_PROVIDER_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `VISION_MCP_PROVIDER_API_KEY` | API 密钥（本地服务可留空） | `sk-xxx` |
| `VISION_MCP_PROVIDER_MODEL` | 模型名称 | `gpt-4o` |
| `VISION_MCP_PROVIDER_NAME` | provider 名称（可选） | `my-provider` |

其他通用环境变量：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `MAX_IMAGE_SIZE_MB` | 图片大小上限 (MB) | `20` |
| `MAX_VIDEO_SIZE_MB` | 视频大小上限 (MB) | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | 视频时长上限 (分钟) | `120` |
| `VISION_MCP_TRANSPORT` | 传输模式 | `stdio` |
| `VISION_MCP_CONFIG` | 配置文件路径 | 自动发现 |
| `VISION_MCP_LOG_LEVEL` | 日志级别 | `INFO` |

### stdio vs SSE：两种传输模式怎么选？

| | stdio 模式 | SSE 模式 |
|---|---|---|
| **谁启动服务** | 编辑器自动启动 | 你自己手动启动 |
| **生命周期** | 编辑器关了就停 | 独立进程，一直在跑 |
| **适合谁** | Claude Code | Cursor / Windsurf / Claude Desktop |
| **配置方式** | 写 command + args | 写 URL 地址 |

简单说：**Claude Code 用 stdio，其他用 SSE**。

---

## 安全机制

MCP Server 会被 AI 客户端调用来读取文件和访问 URL，所以安全至关重要。

**路径白名单** — 只允许读取 `allowed_paths` 中列出的目录。默认只有 `~`（家目录）和 `/tmp`。路径解析会跟随符号链接，symlink 绕过攻击会被阻止。

**SSRF 防护** — 自动拦截对内网地址的 URL 请求：
- 环回地址（`localhost`、`127.0.0.1`、`::1`）
- 私有网段（`10.x.x.x`、`172.16-31.x.x`、`192.168.x.x`）
- 云服务商元数据端点（AWS / GCP / Azure / 阿里云）
- 非 HTTP 协议（`file://`、`ftp://` 等）
- HTTP 重定向会逐跳验证，防止重定向到内网

**资源限制** — 文件大小、像素数、重定向次数、超时时间全部有上限，防止资源耗尽攻击。

**MIME 验证** — 通过文件头魔术字节检测真实类型，不信任扩展名。防止恶意文件伪装成图片。

---

## 支持的格式

**图片：** JPEG、PNG、GIF、WebP、BMP、TIFF、HEIC、HEIF、AVIF
- 最大 20 MB / 16 MP（约 4000×4000）
- 超过 4096px 自动降采样

**视频：** MP4、AVI、MOV、MKV、WebM
- 最大 2 GB / 120 分钟
- 帧提取需要安装 OpenCV（`pip3 install opencv-python`）或 ffmpeg

---

## 常见问题

**Q: 报错 `command not found: python` 或 `No module named vision_mcp`？**

Python 路径没对上。终端执行 `which python3`（macOS/Linux）或 `where python`（Windows），把输出的完整路径填到 MCP 配置的 `command` 字段里。例如：
```json
{
  "command": "/opt/homebrew/bin/python3",
  "args": ["-m", "vision_mcp"]
}
```

**Q: 报错 `pip3: command not found`？**

用 `python3 -m pip install .` 代替 `pip3 install .`。

**Q: 我用的模型已经支持图片了（比如 GPT-4o），还需要这个吗？**

如果你的需求只是分析单张图片，可能不需要。但如果你需要视频分析、批量 OCR、多图对比、模型切换、或本地隐私，这个插件能提供这些编辑器本身做不到的能力。

**Q: 怎么同时用多个模型？**

在 `config.yaml` 中配置多个 provider，每个用不同的 `name`：

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

然后在对话中指定：`用 openai 分析这张图片`，或在工具调用时传 `provider: "openai"`。

**Q: 报错 "No providers configured"？**

说明没有配置任何 provider。检查以下几点：
1. 是否在启动目录创建了 `config.yaml`（至少包含一个 provider）
2. 或是否设置了 `VISION_MCP_PROVIDER_*` 环境变量
3. `config.yaml` 中的 `${VAR}` 是否能在环境变量或 `.env` 中找到对应值（缺失会变成空字符串，导致 provider 被跳过）

**Q: 报错 "Path is outside allowed directories"？**

图片路径不在白名单内。在 `config.yaml` 的 `allowed_paths` 中添加图片所在目录。

**Q: 视频分析报错 / 提取不到帧？**

需要安装 OpenCV 或 ffmpeg：
```bash
pip3 install opencv-python   # 推荐
# 或
brew install ffmpeg          # macOS
apt install ffmpeg           # Ubuntu/Debian
```

**Q: SSE 模式启动后客户端连不上？**

确认服务是否正常运行（终端应该显示 `Starting Vision MCP Server`），并检查防火墙是否放行了 8000 端口。

---

## 项目结构

```
mcp-server-vision/
├── src/vision_mcp/
│   ├── server.py          # MCP 服务入口 + 6 个工具定义
│   ├── config.py          # 配置管理（支持 YAML / .env / 环境变量）
│   ├── security.py        # 安全模块（路径白名单 / SSRF 防护 / MIME 检测）
│   ├── media.py           # 媒体加载（图片/视频读取、base64 编码、HTTP 重定向）
│   ├── __main__.py        # python -m 入口
│   └── providers/         # 视觉模型适配层
│       ├── __init__.py
│       └── base.py        # 所有提供商实现（OpenAI / Ollama / Anthropic）
├── tests/                 # 测试用例（152 个）
├── config.yaml.example    # 配置文件示例
├── Dockerfile             # Docker 构建文件
└── pyproject.toml         # 项目元数据和依赖
```

---

## 参与开发

```bash
pip3 install -e ".[dev]"   # 安装开发依赖
pytest                     # 运行测试
pytest --cov=vision_mcp    # 测试 + 覆盖率
ruff check src/            # 代码检查
mypy src/                  # 类型检查
```

---

## 许可证

[MIT License](LICENSE)

---

## 致谢

- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP 协议规范
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP Server 框架
- [httpx](https://www.python-httpx.org/) — 异步 HTTP 客户端
- [Pillow](https://pillow.readthedocs.io/) — 图像处理库
- [OpenCV](https://opencv.org/) — 计算机视觉库
