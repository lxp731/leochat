"""
ChatRoom CLI — prompt_toolkit TUI
═══════════════════════════════════════════════════════════
布局:  [ 标题栏 ]
        [ 消息区 (可滚动) ]
        [   3 行间隔   ]
        [ ── 分隔线 ── ]
        [ 󰞷 username ❯ 输入框 ]

消息对齐: 短用户名自动补空格，确保所有 󰭹 对齐到同一列。
"""
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple

import socketio # type: ignore
from prompt_toolkit import Application # type: ignore
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, ScrollablePane # type: ignore
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl # type: ignore
from prompt_toolkit.key_binding import KeyBindings # type: ignore
from prompt_toolkit.styles import Style # type: ignore
from prompt_toolkit.buffer import Buffer # type: ignore
from prompt_toolkit.layout.screen import Point # type: ignore
from prompt_toolkit.application.current import get_app # type: ignore
from wcwidth import wcswidth # type: ignore

# ── 环境 ──────────────────────────────────────────────

CST = timezone(timedelta(hours=8))


def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


_load_env()
SERVER_IP = os.environ.get("SERVER_IP", "127.0.0.1")
SERVER_PORT = os.environ.get("SERVER_PORT", "5000")
SERVER_URL = os.environ.get("CHAT_SERVER", f"http://{SERVER_IP}:{SERVER_PORT}")


def _now() -> str:
    return datetime.now(CST).strftime("%H:%M")


def _display_w(s: str) -> int:
    """终端显示宽度（CJK 字符宽 2 列，Nerd Font 图标宽 1 列）"""
    return wcswidth(s) or len(s)


# ── prompt_toolkit 样式 ───────────────────────────────

APP_STYLE = Style.from_dict(
    {
        "header.box": "bold cyan",
        "header.title": "bold cyan",
        "header.welcome": "cyan",
        "msg.time": "cyan",
        "msg.self": "bold green",
        "msg.other": "bold yellow",
        "msg.text": "",
        "msg.pad": "",  # 对齐空格，无色
        "msg.system": "bold magenta",
        "msg.error": "bold red",
        "msg.info": "bold magenta",
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
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._users: list = []
        # 消息存储为原始 dict，格式化在 _messages_lines 中统一处理
        self._messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._app: Application | None = None
        self._input_buffer: Buffer | None = None
        self._prompt_str = f"󰞷 {self.username} ❯ "
        self._register_events()

    # ── 线程安全 ──────────────────────────────────────

    def _add(self, msg: Dict[str, Any]):
        """存储原始消息 dict，格式：{type, text, time?, user?, self?}"""
        with self._lock:
            self._messages.append(msg)

    def _invalidate(self):
        """从 socketio 线程触发 UI 刷新"""
        try:
            if self._app and self._app.is_running:
                self._app.invalidate()
        except Exception:
            pass

    # ── socketio 事件 ─────────────────────────────────

    def _register_events(self):
        @self.sio.event
        def connect():
            self.connected = True
            self.sio.emit("join", {"user": self.username})
            self._add({"type": "info", "text": f"󰄬 已连接至服务器: {SERVER_URL}"})
            self._invalidate()

        @self.sio.event
        def disconnect():
            self.connected = False
            self._add({"type": "error", "text": "󰅚 与服务器断开连接"})
            self._invalidate()

        @self.sio.on("message")
        def on_message(data):
            self._add(
                {
                    "type": "chat",
                    "time": data.get("time", _now()),
                    "user": data.get("user", "???"),
                    "text": data.get("text", ""),
                    "self": data.get("user") == self.username,
                }
            )
            self._invalidate()

        @self.sio.on("system")
        def on_system(data):
            content = data.get("text", "")
            icon = "󰋼"
            if "joined" in content:
                icon = "󰶼"
            elif "left" in content:
                icon = "󰶽"
            self._add({"type": "system", "text": f"{icon} {content}"})
            self._invalidate()

        @self.sio.on("error")
        def on_error(data):
            err = data.get("text", "错误")
            self._add({"type": "error", "text": f"󰅚 {err}"})
            self._invalidate()

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))

    # ── UI 回调（在 UI 线程中调用）────────────────────

    def _header_lines(self) -> List[Frag]:
        app = get_app()
        w = app.output.get_size().columns
        box_w = max(w - 2, 10)
        return [
            ("class:header.box", "╭" + "─" * box_w + "╮\n"),
            (
                "class:header.title",
                f"│ {'󰭹 ChatRoom CLI (TUI)':^{box_w}} │\n",
            ),
            (
                "class:header.welcome",
                f"│ {'󱑎 欢迎, ' + self.username + '!':^{box_w}} │\n",
            ),
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
        return result

    def _msg_line_count(self) -> int:
        with self._lock:
            return len(self._messages)

    def _msg_cursor_pos(self):
        n = self._msg_line_count()
        if n == 0:
            return None
        return Point(x=0, y=n)

    def _prompt_lines(self) -> List[Frag]:
        return [("class:input.prompt", self._prompt_str)]

    # ── 发送 ──────────────────────────────────────────

    def _send(self):
        if self._input_buffer is None:
            return
        text = self._input_buffer.text.strip()
        if not text:
            return

        if text.startswith("/"):
            cmd = text[1:].lower()
            if cmd in ("exit", "quit"):
                self.exit_flag = True
                if self._app:
                    self._app.exit()
                return
            if cmd == "users":
                ul = ", ".join(self._users) if self._users else "无"
                self._add({"type": "info", "text": f"󰭿 在线用户: {ul}"})
                self._invalidate()
                self._input_buffer.text = ""
                return
            if cmd == "help":
                self._add({"type": "info", "text": "命令: /users /exit /help"})
                self._invalidate()
                self._input_buffer.text = ""
                return
            self._add({"type": "error", "text": f"未知命令: /{cmd}"})
            self._invalidate()
            self._input_buffer.text = ""
            return

        if self.connected:
            self.sio.emit(
                "send_message",
                {"user": self.username, "text": text, "time": _now()},
            )

        self._input_buffer.text = ""

    # ── 构建 TUI ──────────────────────────────────────

    def build_app(self) -> Application:
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            self._send()

        @kb.add("c-c")
        @kb.add("c-d")
        def _(event):
            self.exit_flag = True
            event.app.exit()

        self._input_buffer = Buffer(
            name="input",
            multiline=False,
            accept_handler=lambda _: None,
        )

        header = Window(
            content=FormattedTextControl(self._header_lines),
            height=4,
            always_hide_cursor=True,
            dont_extend_height=True,
        )

        messages = ScrollablePane(
            content=Window(
                content=FormattedTextControl(
                    self._messages_lines,
                    focusable=False,
                    get_cursor_position=self._msg_cursor_pos,
                ),
                wrap_lines=True,
                always_hide_cursor=True,
            )
        )

        spacer = Window(height=3, char=" ", always_hide_cursor=True)

        divider = Window(
            height=1,
            char="─",
            always_hide_cursor=True,
            style="class:separator",
        )

        prompt_w = len(self._prompt_str)
        input_row = VSplit(
            [
                Window(
                    content=FormattedTextControl(self._prompt_lines),
                    height=1,
                    width=prompt_w,
                    dont_extend_width=True,
                    always_hide_cursor=True,
                ),
                Window(
                    content=BufferControl(buffer=self._input_buffer),
                    height=1,
                ),
            ],
            height=1,
        )

        root = HSplit([header, messages, spacer, divider, input_row])

        self._app = Application(
            layout=Layout(root),
            style=APP_STYLE,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )
        return self._app

    # ── 入口 ──────────────────────────────────────────

    def run(self):
        def connect_sio():
            try:
                self.sio.connect(SERVER_URL, wait_timeout=5)
            except Exception as exc:
                err = str(exc)
                if "refused" in err.lower():
                    self._add({"type": "error", "text": "无法连接服务器: 服务未启动"})
                else:
                    self._add({"type": "error", "text": f"无法连接服务器: {err}"})
                self._invalidate()

        self._add({"type": "info", "text": f"󰄬 正在连接 {SERVER_URL}..."})
        t = threading.Thread(target=connect_sio, daemon=True)
        t.start()

        app = self.build_app()
        try:
            app.run()
        finally:
            self.exit_flag = True
            try:
                self.sio.disconnect()
            except Exception:
                pass


# ── CLI 入口 ──────────────────────────────────────────

def main() -> None:
    print("\033[2J\033[H", end="")
    print("╭──────────────────────────╮")
    print("│     💬 极简聊天室         │")
    print("╰──────────────────────────╯")
    print()
    try:
        username = input("󰙯 请输入您的昵称: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n已取消")
        return

    if not username:
        print("昵称不能为空")
        return

    client = ChatClient(username)
    client.run()
    print("\n再见! 👋")


if __name__ == "__main__":
    main()
