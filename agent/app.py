"""
Leochat AI Agent — 自主聊天机器人
═══════════════════════════════════════════════════════════
使用 DeepSeek API 作为推理后端，以普通用户身份加入聊天室。
自行判断何时发言、说什么内容，不依附于任何人。

拟人聊天算法 — 四状态状态机：
  COOLING ──(6s)──→ IDLE ──(合批窗口)──→ THINKING
    ↑                                       │
    │        发言                            ├──[SILENT]──→ SILENT
    └────────────────────────────────────    │              │
                                            │发言          │条数+时间+概率
                                            └──────────────┘
同 sender 连续发言会被合并在 3s 窗口内，LLM 看到的是同一个人连续说的话。
"""
import enum
import json
import os
import random
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

# ── 拟人节奏参数（从配置文件读取，不硬编码）───────────

COOLDOWN_SECONDS: float = float(cfg["agent"]["cooldown_seconds"])
SILENT_MSG_THRESHOLD: int = int(cfg["agent"]["silent_msg_threshold"])
SILENT_TIME_THRESHOLD: float = float(cfg["agent"]["silent_time_threshold"])
SILENT_PROBABILITY: float = float(cfg["agent"]["silent_probability"])
SAME_SENDER_DEBOUNCE: float = float(cfg["agent"]["same_sender_debounce"])
IDLE_BATCH_WINDOW: float = float(cfg["agent"]["idle_batch_window"])

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


# ═══════════════════════════════════════════════════════
# 拟人聊天状态机
# ═══════════════════════════════════════════════════════


class AgentState(enum.Enum):
    """
    四个状态，模拟真人的聊天节奏：

    COOLING  — 刚说完话，强制冷却。收到消息只记历史，不决策。
    IDLE     — 冷却结束，待命。收到消息启动短合批窗口后决策。
    SILENT   — 上次决策选择了沉默。进入惰性模式，不急于再次决策。
    THINKING — LLM 正在思考中。收到消息只记历史，不排队新决策。
    """
    COOLING = "cooling"
    IDLE = "idle"
    SILENT = "silent"
    THINKING = "thinking"


# ── 状态变量 ──────────────────────────────────────────

_state = AgentState.IDLE
_state_lock = threading.Lock()          # 保护 _state 及关联时间/计数

_last_speak_time = 0.0                  # 上次发言的时间戳（用于 COOLING 判断）
_last_decision_time = 0.0               # 上次决策完成的时间戳（用于 SILENT 时间门槛）
_silent_msg_count = 0                   # SILENT 状态下累积的消息数

_force_pending = False                  # THINKING 期间有人 @agent，标记等思考完再决策

# ── 消息历史 ──────────────────────────────────────────

_history: deque[str] = deque(maxlen=CONTEXT_SIZE + 200)


def format_msg(data: dict) -> str:
    """将消息数据格式化为 LLM 可读的文本行。"""
    user = data.get("user", "???")
    text = data.get("text", "")
    return f"[{user}]: {text}"


# ═══════════════════════════════════════════════════════
# 同 Sender 连续发言合并（Debounce）
# ═══════════════════════════════════════════════════════
#
# 当同一个人短时间内连续发多条消息时，把它们合并到同一个
# 上下文块中，让 LLM 看到 "[A]: ...\n[A]: ..." 的形式，
# 自然感知"这是同一个人在补充说话"，而不是拆成多次独立决策。

_same_sender: str | None = None         # 当前正在缓冲的 sender
_sender_buffer: list[str] = []          # 缓冲的消息行
_sender_timer: threading.Timer | None = None  # debounce 定时器
_sender_lock = threading.Lock()         # 保护 buffer 相关变量


def _cancel_sender_timer():
    """取消同 sender 合并定时器（需在 _sender_lock 内调用）。"""
    global _sender_timer
    if _sender_timer is not None:
        _sender_timer.cancel()
        _sender_timer = None


def _flush_sender_buffer():
    """
    将当前缓冲的同 sender 消息写入历史，然后走状态机评估是否触发决策。
    调用者需持有 _sender_lock。
    """
    global _same_sender, _sender_buffer
    if not _sender_buffer:
        _cancel_sender_timer()
        _same_sender = None
        return

    lines = list(_sender_buffer)
    _sender_buffer.clear()
    _cancel_sender_timer()
    _same_sender = None

    # 写入历史 — 同一人的多条消息连续存放，LLM 看到的就是连续的 [user]: ...
    for line in lines:
        _history.append(line)

    # 走状态机
    _process_incoming(force=False)


def _on_sender_debounce():
    """
    同 sender 合并窗口到期：此人已经 3 秒没发新消息了，flush 进入历史。
    """
    with _sender_lock:
        _flush_sender_buffer()


def _is_mentioned(text: str) -> bool:
    """
    检测消息是否提到了 agent。
    简单的子串匹配 — 如果消息中包含 agent 名字，视为被 @。
    """
    return AGENT_NAME in text


# ═══════════════════════════════════════════════════════
# IDLE 合批定时器
# ═══════════════════════════════════════════════════════
#
# IDLE 状态下收到消息不立刻调 LLM，而是等 IDLE_BATCH_WINDOW 秒。
# 窗口内后续消息合并，窗口到期后一次性调用 LLM。

_idle_timer: threading.Timer | None = None
_idle_lock = threading.Lock()


def _cancel_idle_timer():
    """取消 IDLE 合批定时器（需在 _idle_lock 内调用）。"""
    global _idle_timer
    if _idle_timer is not None:
        _idle_timer.cancel()
        _idle_timer = None


def _start_idle_timer():
    """启动 IDLE 合批定时器（需在 _idle_lock 内调用）。"""
    global _idle_timer
    _cancel_idle_timer()
    _idle_timer = threading.Timer(IDLE_BATCH_WINDOW, _on_idle_timer)
    _idle_timer.daemon = True
    _idle_timer.start()


def _on_idle_timer():
    """IDLE 合批窗口到期 → 进入 THINKING，调用 LLM 决策。"""
    with _idle_lock:
        _idle_timer = None
    _enter_thinking()


# ═══════════════════════════════════════════════════════
# 状态机核心：消息进入时的路由逻辑
# ═══════════════════════════════════════════════════════


def _enter_thinking():
    """
    进入 THINKING 状态，启动 LLM 决策线程。
    所有触发 LLM 决策的路径（IDLE 窗口到期、SILENT 概率中奖、
    @mention 强制唤醒）统一走这个入口。
    """
    with _state_lock:
        # 防止并发进入 — 如果已经在思考就算了
        if _state == AgentState.THINKING:
            return
        _state = AgentState.THINKING

    # LLM 调用可能耗时数秒，放在独立线程中不阻塞 socket.io 事件循环
    t = threading.Thread(target=_do_llm_decision, daemon=True)
    t.start()


def _process_incoming(force: bool = False):
    """
    状态机入口：收到新消息（经过同 sender 合并后）调用此函数。
    
    根据当前状态决定是否触发 LLM 决策：
    - COOLING：冷却中，不决策
    - IDLE：启动合批窗口
    - SILENT：检查惰性条件（条数 + 时间 + 概率）
    - THINKING：已经在思考，不打断

    force=True 时（@mention 触发），绕过所有状态直接进 THINKING。
    """
    if force:
        # @mention 强制唤醒：取消所有等待中的定时器，直接决策
        with _idle_lock:
            _cancel_idle_timer()
        with _state_lock:
            if _state == AgentState.THINKING:
                # 已经在思考中：标记待处理，当前决策完成后自动再跑一轮
                # 当前 LLM 调用已经抓取了历史快照，看不到这条 @mention
                _force_pending = True
                return
        _enter_thinking()
        return

    with _state_lock:
        now = time.time()

        # ── COOLING：刚说过话，冷却期间不理人 ──
        if _state == AgentState.COOLING:
            if now - _last_speak_time >= COOLDOWN_SECONDS:
                # 冷却结束，进入 IDLE，然后继续往下走
                _state = AgentState.IDLE
                print("[STATE] COOLING → IDLE")
            else:
                # 还在冷却，什么都不做
                return

        # ── THINKING：已经在思考，不排队新决策 ──
        if _state == AgentState.THINKING:
            return

        # ── SILENT：沉默惰性 — 不是每条消息都决策 ──
        if _state == AgentState.SILENT:
            _silent_msg_count += 1
            elapsed = now - _last_decision_time

            # 双重门槛：消息条数 AND 时间都必须达标
            if _silent_msg_count >= SILENT_MSG_THRESHOLD and elapsed >= SILENT_TIME_THRESHOLD:
                # 达标后以概率触发 — 不是必触发，更像人
                if random.random() < SILENT_PROBABILITY:
                    print(f"[STATE] SILENT → THINKING (msg={_silent_msg_count}, s={elapsed:.0f})")
                    _enter_thinking()
                    return
                # 没中奖：留在 SILENT，下条消息再抽奖
            return  # 门槛未到或概率没中，继续沉默

        # ── IDLE：待命，启动合批窗口 ──
        if _state == AgentState.IDLE:
            with _idle_lock:
                # 已有定时器则刷新（重新开始计时），否则启动新的
                _start_idle_timer()


# ═══════════════════════════════════════════════════════
# LLM 决策（在线程中运行）
# ═══════════════════════════════════════════════════════


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


def _do_llm_decision():
    """
    执行一次 LLM 决策（在独立线程中运行）。
    
    决策结果决定后续状态：
    - 发言 → COOLING
    - [SILENT] → SILENT（重置惰性计数器）
    - 异常 → IDLE（保守回退，等下次消息再试）
    
    如果 _force_pending 为 True（思考期间有人 @），
    完成后检查并可能立即触发下一轮决策。
    """
    global _force_pending

    # 抓取当前历史快照
    lines = list(_history)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(lines)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tools = [WEB_SEARCH_TOOL] if tavily_client else None

    llm_said_something = False  # 本轮 LLM 是否发了言

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

            # ── 处理 tool calls：执行搜索，结果反馈给 LLM 继续 ──
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
                continue  # 回 LLM 继续决策

            # ── 处理文本回复 ──
            reply = (msg.content or "").strip()
            print(f"[LLM] {reply[:120]}{'...' if len(reply) > 120 else ''}")

            # 判断是否 [SILENT]
            is_silent = (reply.upper().startswith("[SILENT]") or reply == "[SILENT]")

            if is_silent:
                # LLM 选择了沉默
                with _state_lock:
                    _state = AgentState.SILENT
                    _last_decision_time = time.time()
                    _silent_msg_count = 0  # 重置惰性计数器
                print("[STATE] THINKING → SILENT")
            else:
                # 清理可能的 [SILENT] 前缀（LLM 有时输出 "[SILENT] 但我想说..."）
                if reply.startswith("[SILENT]") and len(reply) > 8:
                    reply = reply[8:].strip()

                if reply:
                    # ── 发言 ──
                    sio.emit("send_message", {"text": reply})
                    llm_said_something = True

                    with _state_lock:
                        _state = AgentState.COOLING
                        _last_speak_time = time.time()
                    print(f"[STATE] THINKING → COOLING ({COOLDOWN_SECONDS}s)")
                else:
                    # 空回复视为沉默
                    with _state_lock:
                        _state = AgentState.SILENT
                        _last_decision_time = time.time()
                        _silent_msg_count = 0
                    print("[STATE] THINKING → SILENT (empty reply)")

            break  # 决策完成

        except Exception as exc:
            print(f"[ERROR] LLM 调用失败: {exc}")
            # 异常回退到 IDLE，等下次消息重试
            with _state_lock:
                _state = AgentState.IDLE
                _force_pending = False
            print("[STATE] THINKING → IDLE (error fallback)")
            return

    # ── 决策完成后，检查是否有待处理的 force 请求 ──
    # 场景：THINKING 期间有人 @agent，当前决策结果可能没有回应
    # 此时标记 force_pending，决策完成后立即再跑一轮
    with _state_lock:
        if _force_pending:
            _force_pending = False
            # 如果当前不是在 COOLING（刚发过言），立即再决策
            # 注意：刚发过言进 COOLING 是合理的——说完话了看一眼
            if _state != AgentState.COOLING:
                print("[STATE] 处理 @mention 待处理请求")
                _enter_thinking()


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
    print(f"[+] 已连接 {SERVER_URL}")
    sio.emit("join", {"user": AGENT_NAME})


@sio.event
def disconnect():
    print("[-] 已断开连接")


@sio.on("message")
def on_message(data):
    """
    收到聊天消息的主入口。

    消息处理分为三层：
    1. 过滤：自己的消息、空消息直接跳过
    2. 同 sender 合并：同一人 3 秒内的连续发言合到一起，LLM 看到连续的 [A]: ...
    3. 状态机路由：根据当前状态决定是否触发决策

    特殊路径：@mention 强制唤醒，绕过所有状态直接决策。
    """
    if not isinstance(data, dict):
        return

    user = data.get("user", "")
    if not user:
        return

    line = format_msg(data)

    # ── 自己的消息：只记历史，绝对不触发决策 ──
    if user == AGENT_NAME:
        _history.append(line)
        return

    text = data.get("text", "")

    # ── 检查是否被 @ ──
    mentioned = _is_mentioned(text)

    # ── 同 sender 合并逻辑 ──
    with _sender_lock:
        sender_changed = (_same_sender is not None and _same_sender != user)

        if mentioned:
            # 被 @ 了：flush 当前 buffer（如果有），然后这条消息直接走状态机
            _flush_sender_buffer()
            _history.append(line)
            _process_incoming(force=True)
            return

        if sender_changed:
            # 换人说话了：flush 上一个人的 buffer，开始新 buffer
            _flush_sender_buffer()

        # 加入当前 sender 的 buffer
        if _same_sender is None:
            _same_sender = user
        _sender_buffer.append(line)

        # 重启 debounce 定时器
        _cancel_sender_timer()
        _sender_timer = threading.Timer(SAME_SENDER_DEBOUNCE, _on_sender_debounce)
        _sender_timer.daemon = True
        _sender_timer.start()


@sio.on("system")
def on_system(data):
    if isinstance(data, dict):
        line = f"[系统]: {data.get('text', '')}"
        _history.append(line)
        # 系统消息只记历史，不触发决策


@sio.on("error")
def on_error(data):
    if isinstance(data, dict):
        print(f"[!] 服务器错误: {data.get('text', '未知')}")


@sio.on("announcement")
def on_announcement(data):
    if isinstance(data, dict) and data.get("text"):
        line = f"[公告]: {data['text']}"
        _history.append(line)
        # 公告只记历史，不触发决策


# ── 启动 ──────────────────────────────────────────────

def main():
    print(f"Leochat Agent: {AGENT_NAME}")
    print(f"Server: {SERVER_URL}")
    print(f"Model: {LLM_MODEL}")
    print(f"Context: {CONTEXT_SIZE} messages")
    print(f"Personality: {AGENT_DIR / 'IDENTIFY.md'}")
    print(f"Cooldown: {COOLDOWN_SECONDS}s | "
          f"Silent: {SILENT_MSG_THRESHOLD}msgs/{SILENT_TIME_THRESHOLD}s@{SILENT_PROBABILITY:.0%} | "
          f"Debounce: {SAME_SENDER_DEBOUNCE}s")
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
