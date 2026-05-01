"""
Leochat CLI — prompt_toolkit TUI
═══════════════════════════════════════════════════════════
布局:  [ 标题栏 ]
        [ 消息区 (可滚动) ]
        [ ── 分隔线 ── ]
        [ 󰞷 username ❯ 输入框 ]
"""
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, cast

import socketio
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, ScrollablePane
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.application.current import get_app
from wcwidth import wcswidth

# ── 环境 ──────────────────────────────────────────────

CST = timezone(timedelta(hours=8))


def _load_env():
    # 仅从当前目录加载 .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


_load_env()
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")


def _now() -> str:
    return datetime.now(CST).strftime("%H:%M:%S")


def _display_w(s: str) -> int:
    """终端显示宽度（CJK 字符宽 2 列，Nerd Font 图标宽 1 列）"""
    return wcswidth(s) or len(s)


# ── prompt_toolkit 样式 ───────────────────────────────

APP_STYLE = Style.from_dict(
    {
        "header.box": "bold cyan",
        "header.title": "bold cyan",
        "header.welcome": "cyan",
        "msg.time": "#888888",
        "msg.self": "bold green",
        "msg.other": "bold yellow",
        "msg.system": "bold magenta",
        "msg.error": "bold red",
        "msg.info": "bold blue",
        "msg.pad": "",
        "msg.text": "",
        "input.prompt": "bold cyan",
        "separator": "#555555",
    }
)

# ── 类型别名 ──────────────────────────────────────────

Frag = Tuple[str, str]  # (style_class, text)


# ── ChatClient ────────────────────────────────────────

class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio: Any = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=1,
            reconnection_delay_max=10,
        )
        self.exit_flag = False
        self.connected = False
        self._users: List[str] = []
        
        self._lock = threading.Lock()
        self._app: Application | None = None
        
        self._messages: List[Dict[str, Any]] = []
        self._input_buffer: Buffer | None = None
        
        self._prompt_str = f"󰞷 {self.username} ❯ "
        self._max_user_w = 0
        self._rendered_lines = 1  # 缓存最后一次渲染的行数，防止索引越界
        
        self._register_events()

    # ── 消息处理 ──────────────────────────────────────

    def _add(self, msg: Dict[str, Any]) -> None:
        """存储原始消息 dict，格式：{type, text, time?, user?, self?}"""
        with self._lock:
            self._messages.append(msg)
            # 限制在内存中只保留最新的 1000 条消息
            if len(self._messages) > 1000:
                self._messages = self._messages[-1000:]
        self._invalidate()

    def _invalidate(self) -> None:
        try:
            app = self._app
            if app is not None and app.is_running:
                app.invalidate()
        except:
            pass

    # ── socketio 事件 ─────────────────────────────────

    def _register_events(self) -> None:
        sio: Any = self.sio

        @sio.event
        def connect():
            self.connected = True
            sio.emit("join", {"user": self.username})
            self._add({"type": "info", "text": f"󰄬 已连接至服务器: {SERVER_URL}"})

        @sio.event
        def disconnect():
            self.connected = False
            self._add({"type": "error", "text": "󰅚 与服务器断开连接，尝试自动重连..."})

        @sio.event
        def reconnect():
            self._add({"type": "info", "text": "󰄬 重新连接成功"})

        @sio.on("message")
        def on_message(data):
            if isinstance(data, dict):
                msg = {
                    "type": "chat",
                    "time": data.get("time", _now()),
                    "user": data.get("user", "???"),
                    "text": data.get("text", ""),
                    "self": data.get("user") == self.username,
                }
                self._add(msg)

        @sio.on("system")
        def on_system(data):
            if isinstance(data, dict):
                self._add({"type": "system", "text": f"󰋼 {data.get('text', '')}"})

        @sio.on("error")
        def on_error(data):
            if isinstance(data, dict):
                self._add({"type": "error", "text": f"󰅚 {data.get('text', '未知错误')}"})

        @sio.on("userlist")
        def on_userlist(data):
            if isinstance(data, dict):
                self._users = list(data.get("users", []))

    # ── UI 组件 ───────────────────────────────────────

    def _header_lines(self) -> List[Frag]:
        try:
            app = cast(Application, get_app())
            w = app.output.get_size().columns
        except:
            w = 80
        box_w = max(w - 2, 10)
        return [
            ("class:header.box", "╭" + "─" * box_w + "╮\n"),
            ("class:header.title", f"│ {'󰭹 Leochat CLI (TUI)':^{box_w}} │\n"),
            ("class:header.welcome", f"│ {'󱑎 欢迎, ' + self.username + '!':^{box_w}} │\n"),
            ("class:header.box", "╰" + "─" * box_w + "╯"),
        ]

    def _messages_lines(self) -> List[Frag]:
        with self._lock:
            msgs = list(self._messages)

        # ── 第一遍：计算聊天消息中"󰙯 用户名"的最大显示宽度 ──
        max_user_w = 0
        for m in msgs:
            if m["type"] == "chat":
                label = "你" if m.get("self") else m["user"]
                w = _display_w(f"󰙯 {label}")
                if w > max_user_w:
                    max_user_w = w

        # ── 第二遍：格式化每条消息 ──
        result: List[Frag] = []
        for m in msgs:
            t = m["type"]
            if t == "chat":
                ts = m["time"]
                label = "你" if m.get("self") else m["user"]
                style = "msg.self" if m.get("self") else "msg.other"
                user_block = f"󰙯 {label}"
                pad_n = max_user_w - _display_w(user_block)

                result.append(("class:msg.time", f"󱑎 {ts}  "))
                result.append((f"class:{style}", user_block))
                if pad_n > 0:
                    result.append(("class:msg.pad", " " * pad_n))
                result.append(("class:msg.pad", " "))
                result.append(("class:msg.text", f"󰭹 {m['text']}"))
            elif t == "system":
                result.append(("class:msg.system", m["text"]))
            elif t == "info":
                result.append(("class:msg.info", m["text"]))
            elif t == "error":
                result.append(("class:msg.error", m["text"]))
            result.append(("", "\n"))
        
        # 为了美观，如果没有消息则显示占位符
        if not result:
            result.append(("class:msg.time", "没有消息...\n"))
            
        # ── 第三遍：精确计算真实的换行符数量，保证光标定位不越界 ──
        newline_count = sum(text.count('\n') for _, text in result)
        self._target_y = newline_count
        
        return result

    def _prompt_lines(self) -> List[Frag]:
        return [("class:input.prompt", self._prompt_str)]

    def _send(self):
        if not self._input_buffer: return
        text = self._input_buffer.text.strip()
        if not text: return

        if text.startswith("/"):
            cmd = text[1:].lower()
            if cmd in ("exit", "quit"):
                self.exit_flag = True
                if self._app: self._app.exit()
                return
            if cmd == "users":
                ul = ", ".join(self._users) if self._users else "无"
                self._add({"type": "info", "text": f"󰄬 在线用户: {ul}"})
                self._input_buffer.text = ""
                return
            if cmd == "help":
                self._add({"type": "info", "text": "󰄬 命令: /users /exit /help"})
                self._input_buffer.text = ""
                return
            self._add({"type": "error", "text": f"󰅚 未知命令: /{cmd}"})
            self._input_buffer.text = ""
            return

        if self.connected:
            self.sio.emit("send_message", {"text": text})
        else:
            self._add({"type": "error", "text": "󰅚 未连接服务器，发送失败"})
        
        self._input_buffer.text = ""

    def _msg_cursor_pos(self) -> Point | None:
        # 直接使用刚才渲染时计算出的最准确的行索引
        y = getattr(self, '_target_y', 0)
        return Point(x=0, y=y)

    def build_app(self) -> Application:
        kb = KeyBindings()
        @kb.add("enter")
        def _(event): self._send()
        @kb.add("c-c")
        @kb.add("c-d")
        def _(event):
            self.exit_flag = True
            event.app.exit()

        self._input_buffer = Buffer(name="input", multiline=False, accept_handler=lambda _: False)

        header = Window(content=FormattedTextControl(self._header_lines), height=4, dont_extend_height=True)
        
        messages = ScrollablePane(
            content=Window(
                content=FormattedTextControl(
                    self._messages_lines,
                    get_cursor_position=self._msg_cursor_pos,
                ),
                wrap_lines=True,
                always_hide_cursor=True,
            )
        )

        divider = Window(height=1, char="─", style="class:separator", dont_extend_height=True)
        
        prompt_w = len(self._prompt_str)
        input_row = VSplit([
            Window(content=FormattedTextControl(self._prompt_lines), width=prompt_w, dont_extend_width=True, always_hide_cursor=True),
            Window(content=BufferControl(buffer=self._input_buffer)),
        ], height=1)

        root = HSplit([header, messages, divider, input_row])

        self._app = Application(
            layout=Layout(root, focused_element=input_row),
            style=APP_STYLE,
            key_bindings=kb,
            full_screen=True,
            mouse_support=True,
        )
        return self._app

    def run(self):
        def connect_sio():
            try:
                self.sio.connect(SERVER_URL, wait_timeout=5)
            except Exception as exc:
                self._add({"type": "error", "text": f"󰅚 连接失败: {exc}"})

        t = threading.Thread(target=connect_sio, daemon=True)
        t.start()

        app = self.build_app()
        try:
            app.run()
        finally:
            self.exit_flag = True
            try: self.sio.disconnect()
            except: pass


def main() -> None:
    print("\033[2J\033[H", end="")
    print("╭──────────────────────────╮")
    print("│     💬 Leochat CLI        │")
    print("╰──────────────────────────╯")
    print()
    try:
        username = input("󰙯 请输入您的昵称: ").strip()
    except (KeyboardInterrupt, EOFError):
        return

    if not username:
        print("昵称不能为空")
        return

    client = ChatClient(username)
    client.run()
    print("\n再见! 👋")


if __name__ == "__main__":
    main()
