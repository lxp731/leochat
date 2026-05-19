"""
Leochat AI Agent — 自主聊天机器人
═══════════════════════════════════════════════════════════
使用 DeepSeek API 作为推理后端，以普通用户身份加入聊天室。
自行判断何时发言、说什么内容，不依附于任何人。

规则：
- 历史消息（服务端标记 history=True）只响应 @mention，其他丢弃
- 自己的消息只记历史，不触发决策
- 当前正在思考时后来的消息排队，思考完补看
"""
import json
import os
import sys
import time
import threading
import tomllib
from pathlib import Path
from collections import deque

import socketio
from openai import OpenAI

# ── 路径 ──────────────────────────────────────────────

AGENT_DIR = Path(__file__).parent

# ── 加载配置 ──────────────────────────────────────────

cfg_path = AGENT_DIR / "config.toml"
if not cfg_path.exists():
    print(f"配置文件不存在: {cfg_path}")
    print("请创建 config.toml 文件，可参考示例配置。")
    sys.exit(1)

with open(cfg_path, "rb") as f:
    cfg = tomllib.load(f)

SERVER_URL = f"http://{cfg['server']['host']}:{cfg['server']['port']}"

AGENT_NAME = cfg["agent"]["name"]
CONTEXT_SIZE: int = cfg["agent"]["context_size"]

# ── LLM 配置 ──────────────────────────────────────────

LLM_API_BASE = cfg["llm"]["api_base"]
LLM_MODEL = cfg["llm"]["model"]
LLM_TEMP = float(cfg["llm"].get("temperature", 0.9))
LLM_MAX_TOKENS = int(cfg["llm"].get("max_tokens", 512))

# ── 加载人设 ──────────────────────────────────────────

identity_path = AGENT_DIR / "IDENTIFY.md"
if not identity_path.exists():
    print(f"人设文件不存在: {identity_path}")
    print("请创建 IDENTIFY.md 文件，写入 agent 的人设描述。")
    sys.exit(1)

with open(identity_path, "r") as f:
    PERSONALITY = f.read().strip()

# ── LLM 客户端 ────────────────────────────────────────

api_key = cfg.get("llm", {}).get("api_key") or os.environ.get("DEEPSEEK_API_KEY")
if not api_key:
    print("环境变量 $DEEPSEEK_API_KEY 未设置")
    sys.exit(1)

client = OpenAI(api_key=api_key, base_url=LLM_API_BASE)

# ── Web 搜索 (Tavily) ──────────────────────────────────

tavily_api_key = cfg.get("tavily", {}).get("api_key") or os.environ.get("TAVILY_API_KEY")
tavily_client = None
if tavily_api_key:
    try:
        from tavily import TavilyClient
        tavily_client = TavilyClient(api_key=tavily_api_key)
        print("[+] Tavily 搜索已启用")
    except ImportError:
        print("[!] tavily-python 未安装，搜索功能不可用")
    except Exception as exc:
        print(f"[!] Tavily 初始化失败: {exc}")

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索互联网获取实时信息。遇到不懂的梗、缩写、新闻事件、技术概念、"
            "冷知识等需要查证的内容时使用。就像群友不懂的时候掏出手机搜一下。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题",
                }
            },
            "required": ["query"],
        },
    },
}


def execute_web_search(query: str) -> str:
    """执行 Tavily 搜索，返回格式化的结果文本。"""
    if not tavily_client:
        return "搜索功能未配置"
    try:
        resp = tavily_client.search(query, max_results=5)
        results = resp.get("results", [])
        if not results:
            return "没有找到相关结果"
        lines = []
        for r in results[:5]:
            title = r.get("title", "")
            content = r.get("content", "")
            lines.append(f"- {title}\n  {content[:300]}")
        return "\n\n".join(lines)
    except Exception as exc:
        return f"搜索失败: {exc}"


def build_system_prompt() -> str:
    return f"""{PERSONALITY}

---
工具使用说明：
你可以使用 web_search 工具搜索互联网来获取实时信息。
当你不懂某个梗、不确定某个事实、想了解某个话题背景时，用它搜索，就像人拿手机查东西一样。
搜到的信息用来帮助你理解上下文和自然地参与讨论，不要大段搬运搜索内容，也不要说"我搜了一下"之类的话。
搜索不到的或不确定的，直接在聊天中说"不太清楚"就好。

---
输出格式规则（严格遵守）：
每一轮，你会看到最近一段时间的聊天记录。
- 如果你决定不说话，只回复一个词： [SILENT]
- 如果你决定说话，直接回复你的发言内容（纯文本，不要加前缀或引号）
- 不要输出任何其他内容，不要解释你的决策过程
- 你回复的内容会直接出现在聊天室里，所以不要有多余的东西"""


def build_user_prompt(history_lines: list[str]) -> str:
    recent = "\n".join(history_lines[-CONTEXT_SIZE:])
    return f"""以下是最近聊天记录：

{recent}

---
根据以上聊天记录，你现在想说点什么？
- 如果不想说话，只回复: [SILENT]
- 如果想说话，直接回复你想说的内容"""


# ── 消息历史 ──────────────────────────────────────────

_history: deque[str] = deque(maxlen=CONTEXT_SIZE + 200)


def format_msg(data: dict) -> str:
    """将消息数据格式化为 LLM 可读的文本行。"""
    user = data.get("user", "???")
    text = data.get("text", "")
    return f"[{user}]: {text}"


def _is_mentioned(text: str) -> bool:
    """检测消息是否提到了 agent。"""
    return AGENT_NAME in text


# ── 决策调度 ──────────────────────────────────────────

_thinking = False
_pending = False
_lock = threading.Lock()


def _maybe_decide():
    """如果当前没在思考，启动决策线程；否则标记待处理。"""
    global _thinking, _pending
    with _lock:
        if _thinking:
            _pending = True
            return
        _thinking = True
    t = threading.Thread(target=_do_decision, daemon=True)
    t.start()


def _do_decision():
    """执行一次 LLM 决策（在独立线程中运行）。"""
    global _thinking, _pending

    # 抓取当前历史快照
    lines = list(_history)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(lines)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tools = [WEB_SEARCH_TOOL] if tavily_client else None

    for _round in range(3):
        try:
            kwargs = {
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": LLM_TEMP,
                "max_tokens": LLM_MAX_TOKENS,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            resp = client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            # ── 处理 tool calls ──
            if msg.tool_calls:
                messages.append(msg)
                for tc in msg.tool_calls:
                    if tc.function.name == "web_search":
                        args = json.loads(tc.function.arguments)
                        result = execute_web_search(args.get("query", ""))
                        print(f"[SEARCH] {args.get('query', '')[:80]}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                continue

            # ── 处理文本回复 ──
            reply = (msg.content or "").strip()
            print(f"[LLM] {reply[:120]}{'...' if len(reply) > 120 else ''}")

            is_silent = (reply.upper().startswith("[SILENT]") or reply == "[SILENT]")

            if not is_silent:
                if reply.startswith("[SILENT]") and len(reply) > 8:
                    reply = reply[8:].strip()
                if reply:
                    sio.emit("send_message", {"text": reply})

            break

        except Exception as exc:
            print(f"[ERROR] LLM 调用失败: {exc}")
            break

    # ── 决策完成，检查是否有排队消息 ──
    with _lock:
        _thinking = False
        if _pending:
            _pending = False
            _thinking = True
            t = threading.Thread(target=_do_decision, daemon=True)
            t.start()


# ═══════════════════════════════════════════════════════
# Socket.IO 事件处理
# ═══════════════════════════════════════════════════════

sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0,
    reconnection_delay=3,
    reconnection_delay_max=30,
)


@sio.event
def connect():
    _history.clear()
    print(f"[+] 已连接 {SERVER_URL}")
    sio.emit("join", {"user": AGENT_NAME})


@sio.event
def disconnect():
    print("[-] 已断开连接")


@sio.on("message")
def on_message(data):
    if not isinstance(data, dict):
        return

    user = data.get("user", "")
    if not user:
        return

    line = format_msg(data)

    # ── 自己的消息：只记历史 ──
    if user == AGENT_NAME:
        _history.append(line)
        return

    text = data.get("text", "")

    # ── 历史消息：只响应 @mention ──
    if data.get("history"):
        if _is_mentioned(text):
            _history.append(line)
            _maybe_decide()
        return

    # ── 实时消息：记历史，触发决策 ──
    _history.append(line)
    _maybe_decide()


@sio.on("system")
def on_system(data):
    if isinstance(data, dict):
        line = f"[系统]: {data.get('text', '')}"
        _history.append(line)


@sio.on("error")
def on_error(data):
    if isinstance(data, dict):
        print(f"[!] 服务器错误: {data.get('text', '未知')}")


@sio.on("announcement")
def on_announcement(data):
    if isinstance(data, dict) and data.get("text"):
        line = f"[公告]: {data['text']}"
        _history.append(line)


# ── 启动 ──────────────────────────────────────────────

def main():
    print(f"Leochat Agent: {AGENT_NAME}")
    print(f"Server: {SERVER_URL}")
    print(f"Model: {LLM_MODEL}")
    print(f"Context: {CONTEXT_SIZE} messages")
    print(f"Personality: {AGENT_DIR / 'IDENTIFY.md'}")
    print()

    try:
        sio.connect(SERVER_URL, wait_timeout=10)
        sio.wait()
    except KeyboardInterrupt:
        print("\n再见!")
    except Exception as exc:
        print(f"连接失败: {exc}")
        sys.exit(1)
    finally:
        try:
            sio.disconnect()
        except:
            pass


if __name__ == "__main__":
    main()
