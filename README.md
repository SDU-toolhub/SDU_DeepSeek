# 注意
> 本工具仅供技术研究，使用者应于24小时内删除从山东大学DeepSeek获取的非公开数据。开发者不对任何学术诚信审查问题负责，请优先联系信息化办公室申请官方API权限。
> 本程序不保证您的信息安全，使用者应自行承担风险。请勿将本程序用于非法用途，否则后果自负。
> 开发者不对使用本程序导致的任何问题负责。
> 请勿滥用！！！

# 鸣谢

感谢山东大学数智化支撑研究院（信息办）为山大学子提供的免费DeepSeek服务。

感谢@zeroHYH同学为本程序提供山大统一身份认证的登录支持，使得免于使用网页填表。

# 程序开发宗旨

本程序的目的是为了方便使用DeepSeek的同学，提供一个**OpenAI 兼容的 API 服务端**，方便嵌入到翻译工具、IDE 插件（如 OpenCode、Continue）、聊天客户端（如 NextChat、LobeChat）等第三方工具中。

# 特性

- **OpenAI 兼容 API**：支持 `/v1/chat/completions` 和 `/v1/models`，任何 OpenAI 兼容客户端可直接接入
- **多模型支持**：DeepSeek-V4、GLM5.0、MiniMax-M2.5、Doubao-Seed-2.0-pro、Qwen3 等
- **流式输出**：标准 SSE 流式响应，支持打字机效果
- **工具调用（Function Calling）**
- **深度思考模型**：支持 `reasoning_content` 推理内容输出（如 DeepSeek-R1）
- **交互式 CLI**：自带命令行对话工具，支持 readline、历史输入、方向键、中文退格
- **登录态持久化**：自动保存 cookies，避免每次重启都重新登录

---

# 使用方法

## 方式一：使用打包好的程序（推荐）

直接从 **右边** 的 `Releases` 下载最新版本的程序，解压后运行即可。

```bash
# Windows
cli_chat.exe

# Linux / macOS
python cli_chat.py
```

第一次启动会要求输入学号和密码（山大统一身份认证），登录成功后自动生成 `cookies.json` 保存登录态。

如果长时间未使用，登录状态可能会过期，此时请删除 `cookies.json` 重新启动程序。

---

## 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone <仓库地址>
cd SDU_DeepSeek

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行 CLI（会自动拉起本地 API 服务）
python cli_chat.py

# 或者只启动 API 服务端（供第三方客户端连接）
python main.py
```

---

## CLI 命令说明

启动 `cli_chat.py` 后进入交互式对话：

```
=== 山东大学AI助手CLI对话工具 ===
输入 'quit' 或 'exit' 退出
输入 'clear' 清空对话历史
输入 'model' 切换模型
输入 'tools' 开启/关闭工具调用
```

| 命令 | 说明 |
|------|------|
| `quit` / `exit` | 退出程序 |
| `clear` | 清空当前对话历史 |
| `model` | 切换模型（从列表中选择） |
| `tools` | 开启/关闭工具调用 |

---

## 第三方客户端配置

任何支持 OpenAI API 的客户端均可接入，配置如下：

| 配置项 | 值 |
|--------|-----|
| **Base URL** | `http://127.0.0.1:8000/v1` |
| **API Key** | 任意填写（如 `sk-sdu`） |
| **Model** | 从 `/v1/models` 列表中选择 |

### 推荐的第三方客户端

- **OpenCode**（VS Code 插件）
- **Continue**（VS Code / JetBrains 插件）
- **ChatGPT-Next-Web / LobeChat**（Web UI）
- **沉浸式翻译**（浏览器插件）

> ⚠️ **注意**：Base URL 必须以 `/v1` 结尾，否则会出现 404。

---

## 支持的模型

| 模型 ID | 说明 |
|---------|------|
| `deepseek-ai/DeepSeek-V4` | DeepSeek V4（最新旗舰） |
| `deepseek-ai/DeepSeek-V3.2` | DeepSeek V3.2 |
| `deepseek-ai/DeepSeek-R1` | DeepSeek R1（深度思考） |
| `deepseek-ai/DeepSeek-V3` | DeepSeek V3 |
| `deepseek-ai/DeepSeek-V3.2-think` | DeepSeek V3.2 + 深度思考 |
| `Zhipu/GLM5.0` | 智谱 GLM5.0 |
| `MiniMax/MiniMax-M2.5` | MiniMax M2.5 |
| `Doubao/Doubao-Seed-2.0-pro` | 豆包 Seed 2.0 Pro |
| `Qwen/Qwen3-235B-A22B-Instruct` | Qwen3 235B |
| `Qwen/Qwen3-235B-A22B-Thinking` | Qwen3 235B + 深度思考 |

---

## API 请求示例

### 非流式请求

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

### 流式请求

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

### 工具调用请求

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4",
    "messages": [{"role": "user", "content": "1+1=?"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "calculator",
          "description": "计算器",
          "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}
        }
      }
    ]
  }'
```

服务端返回 `finish_reason="tool_calls"` 和工具调用信息后，客户端需自行执行工具函数，再把结果以 `role="tool"` 发回获取最终答案。

---

## 特殊参数

### thinking_budget

思考预算，默认 `1000`，仅对支持深度思考的模型有效（如 DeepSeek-R1、Qwen3-Thinking）：

```json
{
  "model": "deepseek-ai/DeepSeek-R1",
  "messages": [{"role": "user", "content": "请解释量子力学"}],
  "thinking_budget": 2000,
  "stream": true
}
```

---

## 推理内容 (Reasoning Content)

对于支持深度思考的模型（如 DeepSeek-R1、Qwen3-Thinking），响应中会包含 `reasoning_content` 字段：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "这是回答内容",
      "reasoning_content": "这是思考过程"
    }
  }]
}
```

在 CLI 中，推理内容会以 `[思考]: ` 前缀打印。

---

## 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                      第三方客户端                            │
│  (OpenCode / Continue / NextChat / 沉浸式翻译 / curl ...)   │
└──────────────────────┬──────────────────────────────────────┘
                       │ OpenAI API (http://127.0.0.1:8000/v1)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     main.py (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ /v1/models   │  │ /v1/chat/    │  │ 工具调用代理 │      │
│  │              │  │ completions  │  │ (解析tool_call│     │
│  └──────────────┘  └──────┬───────┘  └──────────────┘      │
│                           │                                  │
│                           ▼                                  │
│                      sduwrap.py                              │
│              (multipart/form-data → SSE)                     │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS
                            ▼
                   aiassist.sdu.edu.cn
```

**设计要点**：
- 服务端**不执行实际工具函数**，只负责把 `<tool_call>` 标签解析成标准 `tool_calls` 返回
- 工具执行由**客户端**（如 `cli_chat.py`）自行实现，确保任何 OpenAI 兼容客户端都能连接
- SDU 后端不支持 `role="tool"` 和 `role="system"`，由 `sduwrap.py` 做格式桥接

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 服务端，OpenAI 兼容 API |
| `cli_chat.py` | 交互式 CLI 客户端 |
| `sduwrap.py` | SDU 平台底层封装（SSE 解析、格式桥接） |
| `sdu_aiassist_login.py` | 山大统一身份认证登录 |
| `uniform_login_des.py` | DES 加密辅助 |
| `cookies.json` | 持久化登录态（自动生成） |
| `fingerprint.txt` | 设备指纹（自动生成） |
| `.cli_history` | CLI 输入历史（自动生成） |
| `server.log` | 服务端日志 |

---

## 常见问题

**Q: 启动时提示 cookies 过期？**
A: 删除 `cookies.json` 文件，重新运行程序会引导重新登录。

**Q: 第三方客户端连接报 404？**
A: 检查 Base URL 是否以 `/v1` 结尾，如 `http://127.0.0.1:8000/v1`。

**Q: 模型返回空内容？**
A: 某些模型（如 GLM5.0）对中文 tool prompt 可能冲突，服务端已自动 fallback 到普通对话。

**Q: 如何关闭工具调用？**
A: 在 CLI 中输入 `tools` 切换；在第三方客户端中不配置 `tools` 参数即可。
