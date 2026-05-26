# Vision MCP Server

[English](README_EN.md) | **中文**

让你的 AI 编程工具能够「看懂」图片和视频。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![MCP](https://img.shields.io/badge/MCP-1.0+-green.svg)

---

## 它是什么？

一句话：**一个独立的视觉处理插件**，通过 [MCP 协议](https://modelcontextprotocol.io/)（Model Context Protocol）接入你的 AI 编辑器。

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

## 3 步上手

### 第一步：安装

需要 Python 3.11+。终端执行 `python3 --version` 确认版本。

```bash
git clone https://github.com/xiaoshengwpp/mcp-server-vision.git
cd mcp-server-vision
pip3 install .             # 如果提示 pip3 找不到，改用 python3 -m pip install .
```

安装后记住 Python 的完整路径（Claude Code stdio 模式要用）：

```bash
which python3              # macOS / Linux，记住输出的完整路径
where python               # Windows
```

### 第二步：配置视觉模型

> **Claude Code 用户（stdio 模式）** 可跳过这一步，第三步中通过 `env` 字段配置即可，不需要创建 config.yaml。

在 **mcp-server-vision 目录**（即 `pip3 install .` 所在的目录）创建 `config.yaml`：

```yaml
providers:
  - name: dashscope # 自定义名称，随意取，用于在工具调用中指定该 provider
    type: openai # openai 兼容接口统一填 openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-你的key
    model: qwen-vl-max
    is_default: true # 设为默认 provider

# 额外允许访问的目录（~ 和 /tmp 始终允许，这里添加额外的目录）
allowed_paths:
  - ~/Desktop
  - ~/Documents
  - ~/Downloads
```

> **注意：** config.yaml 从启动服务的目录加载。如果你在其他目录启动服务，需要把 config.yaml 放在那个目录下。

> **其他服务商怎么填？** 改 `base_url`、`api_key`、`model` 三处就行。`name` 随意取。

| 服务商                     | type        | base_url                                            | model 示例                   | 获取 Key                                                              |
| -------------------------- | ----------- | --------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------- |
| 阿里云百炼                 | `openai`    | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max`                | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com/) |
| OpenAI                     | `openai`    | `https://api.openai.com/v1`                         | `gpt-4o`                     | [platform.openai.com](https://platform.openai.com/api-keys)           |
| DeepSeek                   | `openai`    | `https://api.deepseek.com/v1`                       | `deepseek-chat`              | [platform.deepseek.com](https://platform.deepseek.com/)               |
| Anthropic                  | `anthropic` | 默认官方，可填第三方中转地址                        | `claude-3-5-sonnet-20241022` | [console.anthropic.com](https://console.anthropic.com/)               |
| vLLM / LM Studio / LocalAI | `openai`    | 你部署的地址（如 `http://localhost:8000/v1`）       | 你的模型名                   | 自行部署，api_key 留空                                                |

**Anthropic 用户**，`type` 改为 `anthropic`，`base_url` 可以不填（默认官方 API）。使用第三方中转服务时填中转地址即可：

```yaml
providers:
  - name: anthropic
    type: anthropic
    # base_url: https://你的中转地址/v1    # 第三方中转服务才需要，官方 API 不用填
    api_key: sk-ant-你的key
    model: claude-3-5-sonnet-20241022
    is_default: true
```

**本地服务**（vLLM / LM Studio / LocalAI），`api_key` 留空即可：

```yaml
providers:
  - name: local
    type: openai
    base_url: http://localhost:8000/v1
    api_key: ""
    model: Qwen/Qwen2-VL-7B-Instruct
    is_default: true
```

> **不想明文写 Key？** 在同目录创建 `.env` 文件存放密钥，config.yaml 中用 `${VAR}` 引用：
>
> ```env
> # .env（和 config.yaml 同目录）
> DASHSCOPE_API_KEY=sk-你的真实key
> ```
>
> ```yaml
> # config.yaml
> providers:
>   - name: dashscope
>     type: openai
>     base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
>     api_key: ${DASHSCOPE_API_KEY} # 自动从 .env 读取
>     model: qwen-vl-max
>     is_default: true
> ```

### 第三步：接入编辑器

根据编辑器类型选一种：

<details>
<summary><b>推荐：Cursor / Windsurf / Claude Desktop</b>（SSE 模式）</summary>

**1. 确保已创建 config.yaml（第二步），然后在 mcp-server-vision 目录下启动服务：**

```bash
# macOS / Linux
VISION_MCP_TRANSPORT=sse python3 -m vision_mcp

# Windows (PowerShell)
$env:VISION_MCP_TRANSPORT="sse"; python3 -m vision_mcp
```

看到 `Starting Vision MCP Server (transport=sse)` 就成功了。**终端不要关。**

**2. 在编辑器中添加 MCP 服务：**

**Cursor：** Settings → MCP → Add new MCP server → Type 选 `sse`，URL 填 `http://localhost:8000/sse`

**Windsurf：** 编辑 `~/.codeium/windsurf/mcp_config.json`：

```json
{
  "mcpServers": {
    "vision": {
      "serverUrl": "http://localhost:8000/sse"
    }
  }
}
```

**Claude Desktop：** 编辑配置文件（macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows: `%APPDATA%\Claude\claude_desktop_config.json`）：

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
<summary><b>Claude Code</b>（stdio 模式 — 不用手动启动服务）</summary>

不需要创建 config.yaml，所有配置通过 `env` 字段完成。编辑项目根目录的 `.mcp.json`（或全局 `~/.claude.json`）：

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
        "VISION_MCP_PROVIDER_MODEL": "qwen-vl-max",
        "VISION_MCP_PROVIDER_MAX_TOKENS": "2000"
      }
    }
  }
}
```

> 把 `"command"` 替换为第一步 `which python3` 输出的完整路径。
>
> 其他服务商只需改 `BASE_URL`、`API_KEY`、`MODEL` 三个值。**Anthropic 用户**把 `PROVIDER_TYPE` 改为 `anthropic`，`PROVIDER_BASE_URL` 不填（默认官方）或填第三方中转地址。
>
> `VISION_MCP_PROVIDER_MAX_TOKENS` 可选，控制模型最大输出长度。OCR 任务建议设为 `4000` 以上。默认 `2000`。

stdio 模式由编辑器自动管理进程，不需要手动启动服务。

</details>

### 试试看

配置完成后，在对话中直接提及图片：

```
帮我看看这个报错截图是什么意思：~/Desktop/error.png
```

```
提取这张发票截图中的所有文字：~/Desktop/invoice.jpg
```

```
帮我对比这两张截图有什么不同：~/Desktop/v1.png 和 ~/Desktop/v2.png
```

> 本地图片路径需在 `allowed_paths` 白名单内（默认允许 `~` 和 `/tmp`）。

---

## 本地 Ollama 方案

如果你不想用云服务 API，可以用 Ollama 在本地跑视觉模型，图片不离开你的电脑。

1. 安装 Ollama：[ollama.com](https://ollama.com/)
2. 拉取模型：`ollama pull llava`
3. config.yaml 改为：

```yaml
providers:
  - name: local
    type: ollama
    base_url: http://localhost:11434
    api_key: ""
    model: llava
    is_default: true
```

启动和接入方式与上面完全一样。

---

## 切换模型

**改配置文件（永久生效）：** 修改 config.yaml 中 `model` 字段，重启服务即可。

**调用时指定（临时切换）：** 每个工具都支持 `model` 参数：

```
用 qwen-vl-plus 分析这张图片：~/Desktop/photo.jpg
```

**百炼平台可用模型**（共用同一个 API Key）：

| 模型 ID                   | 说明                               |
| ------------------------- | ---------------------------------- |
| `qwen-vl-max`             | 最强视觉理解，复杂场景首选（默认） |
| `qwen-vl-plus`            | 性价比高，日常分析够用             |
| `qwen2.5-vl-72b-instruct` | 72B 参数，细节更精准               |
| `qwen2.5-vl-32b-instruct` | 32B 参数，平衡性能和成本           |

---

## Docker 部署

```bash
docker build -t mcp-server-vision .
docker run -d -p 8000:8000 \
  -e VISION_MCP_TRANSPORT=sse \
  -e VISION_MCP_PROVIDER_TYPE=openai \
  -e VISION_MCP_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -e VISION_MCP_PROVIDER_API_KEY=sk-你的key \
  -e VISION_MCP_PROVIDER_MODEL=qwen-vl-max \
  -e VISION_MCP_PROVIDER_MAX_TOKENS=2000 \
  mcp-server-vision
```

客户端连接 `http://localhost:8000/sse` 即可。

---

## 可用工具

配置成功后，AI 编辑器会多出以下工具：

| 工具                      | 功能               | 关键参数                                                |
| ------------------------- | ------------------ | ------------------------------------------------------- |
| `analyze_image`           | 分析单张图片       | `source`（必填）、`prompt`、`detail`、`model`           |
| `analyze_multiple_images` | 对比 2-10 张图片   | `sources`（必填）、`prompt`、`model`                    |
| `analyze_video`           | 视频帧分析         | `source`（必填）、`prompt`、`max_frames`(1-50)、`model` |
| `ocr_image`               | 图片文字识别 (OCR) | `source`（必填）、`language`、`model`                   |
| `get_server_status`       | 查看当前配置和模型 | —                                                       |
| `get_supported_formats`   | 查看支持的格式     | —                                                       |

> 所有分析工具都支持 `provider` 参数，可指定使用哪个服务商（对应 config.yaml 中的 `name`）。配置了多个 provider 时有用。

---

## 安全机制

- **路径白名单** — 只能读取 `allowed_paths` 中的目录，symlink 绕过攻击会被阻止
- **SSRF 防护** — 自动拦截内网地址、云元数据端点、非 HTTP 协议（仅对用户输入的图片/视频 URL 生效；Provider API 地址自动豁免，Ollama 等本地服务不受影响）
- **资源限制** — 文件大小、像素数、超时时间均有上限
- **MIME 验证** — 通过文件头魔术字节检测真实类型，不信任扩展名

---

## 支持的格式

**图片：** JPEG、PNG、GIF、WebP、BMP、TIFF、HEIC、HEIF、AVIF（最大 20MB / 16MP）

**视频：** MP4、AVI、MOV、MKV、WebM（最大 2GB / 120 分钟，需安装 `pip3 install opencv-python` 或 ffmpeg）

---

## 常见问题

**Q: 报错 `command not found: python` 或 `No module named vision_mcp`？**

Python 路径没对上。执行 `which python3`，把完整路径填到 MCP 配置的 `command` 字段。

**Q: 报错 "No providers configured"？**

1. 检查是否创建了 `config.yaml` 且至少包含一个 provider
2. 检查 `${VAR}` 引用的变量是否有值（缺失会变成空字符串）
3. 如果用环境变量模式，检查 `VISION_MCP_PROVIDER_*` 是否拼写正确

**Q: 报错 "Path is outside allowed directories"？**

家目录（`~`）和 `/tmp` 始终允许访问。如果图片在其他位置（如 `/opt/images`），在 config.yaml 的 `allowed_paths` 中添加对应目录。

**Q: 视频分析报错 / 提取不到帧？**

需要安装 OpenCV 或 ffmpeg：`pip3 install opencv-python` 或 `brew install ffmpeg`。

**Q: SSE 模式启动后连不上？**

确认终端显示 `Starting Vision MCP Server`，检查防火墙是否放行了 8000 端口。

---

## 项目结构

```
mcp-server-vision/
├── src/vision_mcp/
│   ├── server.py          # MCP 服务入口 + 工具定义
│   ├── config.py          # 配置管理（YAML / .env / 环境变量）
│   ├── security.py        # 安全模块（路径白名单 / SSRF / MIME）
│   ├── media.py           # 媒体加载（图片/视频读取）
│   └── providers/         # 视觉模型适配（OpenAI / Anthropic / Ollama）
├── tests/                 # 测试用例
├── config.yaml.example    # 配置文件示例
├── Dockerfile
└── pyproject.toml
```

---

## 参与开发

```bash
pip3 install -e ".[dev]"
pytest                     # 运行测试
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
