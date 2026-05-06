# Leochat Agent

自主聊天机器人，以普通用户身份加入 Leochat 聊天室，使用 LLM 自行判断何时发言、说什么内容。

## 工作原理

```
聊天消息 → Socket.IO → 2s 合批窗口 → LLM 决策
                                        │
                         ┌──────────────┼──────────────┐
                         ▼              ▼              ▼
                      [SILENT]      直接回复      调用 web_search
                      不说话                       ↓
                                               搜索结果 → LLM 再决策 → 回复
```

Agent 通过 WebSocket 连接聊天服务器，监听所有公开消息。收到消息后启动一个 2 秒的合批计时器——窗口内的多条消息会合并为一次 LLM 调用，避免每条消息都触发一次决策。LLM 根据人设和历史记录决定：沉默、发言、或者先搜索再发言。

## 快速开始

### 1. 准备配置文件

```bash
vim config.toml  # 编辑 server.host、agent.name 等
```

### 2. 设置环境变量

```bash
export DEEPSEEK_API_KEY=sk-xxx      # 必需，LLM API key
export TAVILY_API_KEY=tvly-xxx      # 可选，联网搜索功能
```

API key 也可以直接写在 `config.toml` 中（不推荐提交到版本控制）。

### 3. 运行

**本地运行：**

```bash
cd agent
uv sync
uv run python app.py
```

**Docker 运行：**

```bash
# 在项目根目录
docker compose up agent -d
```

首次运行会在控制台看到：

```
Leochat Agent: 小墨
Server: http://server:5000
Model: deepseek-v4-pro
Context: 100 messages
Personality: /app/IDENTIFY.md

[+] Tavily 搜索已启用
[+] 已连接 http://server:5000
```

## 配置说明

`config.toml`：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `server.host` | 聊天服务器地址 | `server`（Docker）/ `127.0.0.1`（本地） |
| `server.port` | 聊天服务器端口 | `5000` |
| `agent.name` | 在聊天室中的显示名称 | `小墨` |
| `agent.context_size` | 每次 LLM 决策参考的消息数 | `100` |
| `llm.api_base` | LLM API 地址 | `https://api.deepseek.com` |
| `llm.model` | 模型名称 | `deepseek-v4-pro` |
| `llm.api_key` | API key（留空则从环境变量读取） | 空 |
| `llm.temperature` | 生成温度（0-2，越高越随机） | `0.9` |
| `llm.max_tokens` | 最大输出 token 数 | `512` |
| `tavily.api_key` | Tavily 搜索 API key（可选） | 空 |

环境变量优先级：`config.toml` 中的 `api_key` 为空时，自动从对应的环境变量读取（`DEEPSEEK_API_KEY`、`TAVILY_API_KEY`）。

## 人设系统

Agent 的性格和行为由 `IDENTIFY.md` 定义。它是一个完整的系统提示词，指导 LLM 如何像一个真实群友一样聊天：

- **说话风格**：口语化、短句为主，杜绝客服/助手语气
- **潜水是常态**：大多数时间不说话，只在想参与时开口
- **有性格**：技术爱好者 + 打工人，有喜好有情绪，不懂就说不懂
- **历史消息处理**：不"挖坟"回复旧消息，像真人爬楼看聊天记录
- **搜索工具使用**：不懂的梗和概念可以搜索，但结果要自然融入对话

修改 `IDENTIFY.md` 即可定制 Agent 的人设，无需改动代码。

## 联网搜索

Agent 支持通过 [Tavily](https://tavily.com/) API 进行联网搜索。配置 `TAVILY_API_KEY` 后，LLM 可以自主决定何时搜索互联网——遇到不懂的梗、缩写、新闻事件或技术概念时，就像群友掏出手机搜一下。

搜索功能是**可选**的，不配置 API key 时 Agent 退化为纯 LLM 决策模式。