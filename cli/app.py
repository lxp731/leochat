"""
Leochat CLI — prompt_toolkit TUI
═══════════════════════════════════════════════════════════
布局:  [ 标题栏 ]
        [ 消息区 (可滚动) ]
        [ ── 分隔线 ── ]
        [ 󰞷 username ❯ 输入框 ]
"""
import argparse
import math
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, cast

import socketio
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.application.current import get_app
from wcwidth import wcswidth

from config import resolve, save, server_url, parse_server_addr, is_first_run, config_path

# ── 环境 ──────────────────────────────────────────────

CST = timezone(timedelta(hours=8))


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
    def __init__(self, username: str, server_url: str):
        self.username = username
        self.server_url = server_url
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
            self._add({"type": "info", "text": f"󰄬 已连接至服务器: {self.server_url}"})

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
                users = data.get("users", [])
                # 兼容新旧格式：新格式 [{"name": ...}], 旧格式 ["name", ...]
                if users and isinstance(users[0], dict):
                    self._users = [u.get("name", "?") for u in users]
                else:
                    self._users = list(users)

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
        """生成消息区的格式化文本。
        
        只渲染消息列表中最后 N 条消息，N 由终端可用行数决定。
        这样新消息始终出现在底部，旧消息自然被顶出视口。
        完全避免 ScrollablePane 的游标滚动问题。
        """
        with self._lock:
            msgs = list(self._messages)

        # ── 获取终端尺寸，计算消息区可用行数 ──
        # 6 行保留区: header(4) + divider(1) + input(1)
        try:
            app = cast(Application, get_app())
            term_w = app.output.get_size().columns
            term_h = app.output.get_size().rows
        except:
            term_w = 80
            term_h = 30
        msg_area_h = max(term_h - 6, 5)

        if not msgs:
            return [("class:msg.time", "没有消息...\n")]

        # ── 第一遍：计算聊天消息中"󰙯 用户名"的最大显示宽度 ──
        max_user_w = 0
        for m in msgs:
            if m["type"] == "chat":
                label = "你" if m.get("self") else m["user"]
                w = _display_w(f"󰙯 {label}")
                if w > max_user_w:
                    max_user_w = w

        # ── 第二遍：格式化每条消息为片段，并估算其占用的显示行数 ──
        # row = (display_lines, fragments_for_this_row)
        rows: List[Tuple[int, List[Frag]]] = []
        for m in msgs:
            fragments: List[Frag] = []
            t = m["type"]
            if t == "chat":
                ts = m["time"]
                label = "你" if m.get("self") else m["user"]
                style = "msg.self" if m.get("self") else "msg.other"
                user_block = f"󰙯 {label}"
                pad_n = max_user_w - _display_w(user_block)

                fragments.append(("class:msg.time", f"󱑎 {ts}  "))
                fragments.append((f"class:{style}", user_block))
                if pad_n > 0:
                    fragments.append(("class:msg.pad", " " * pad_n))
                fragments.append(("class:msg.pad", " "))
                fragments.append(("class:msg.text", f"󰭹 {m['text']}"))
            elif t == "system":
                fragments.append(("class:msg.system", m["text"]))
            elif t == "info":
                fragments.append(("class:msg.info", m["text"]))
            elif t == "error":
                fragments.append(("class:msg.error", m["text"]))

            # 估算消息占用显示行数（考虑 CJK 宽度和终端换行）
            row_text = "".join(text for _, text in fragments)
            row_dw = max(_display_w(row_text), 1)
            dl = math.ceil(row_dw / max(term_w, 1))
            rows.append((dl, fragments))

        # ── 第三遍：从后向前选择消息，直到填满可见区域 ──
        selected: List[List[Frag]] = []
        remaining = msg_area_h
        for dl, fragments in reversed(rows):
            if remaining <= 0:
                break
            selected.append(fragments)
            remaining -= dl
        selected.reverse()

        # ── 组装最终输出的格式化文本 ──
        result: List[Frag] = []
        for fragments in selected:
            for frag in fragments:
                result.append(frag)
            result.append(("", "\n"))

        return result if result else [("class:msg.time", "没有消息...\n")]

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
        
        messages = Window(
            content=FormattedTextControl(self._messages_lines),
            wrap_lines=True,
            always_hide_cursor=True,
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
                self.sio.connect(self.server_url, wait_timeout=5)
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
    # ── CLI 参数 ──
    parser = argparse.ArgumentParser(
        description="Leochat CLI — 轻量聊天终端客户端"
    )
    parser.add_argument(
        "--server", "-s",
        help="服务器地址 (host:port)，例如 192.168.1.100:5000",
    )
    parser.add_argument("--user", "-u", help="用户名")
    args = parser.parse_args()

    # ── 加载配置（优先级：默认值 → config.toml → 环境变量）──
    config = resolve()

    # ── CLI 参数最终覆盖 ──
    if args.server:
        host, port = parse_server_addr(args.server)
        config["server"]["host"] = host
        config["server"]["port"] = port
    if args.user:
        config["user"]["name"] = args.user

    # ── 首次运行：交互式配置 ──
    first_run = not config["user"]["name"]

    if first_run:
        print("\033[2J\033[H", end="")
        print("╭─────────────────────────────────────╮")
        print("│          💬 Leochat CLI              │")
        print("│       首次运行 — 配置向导            │")
        print("╰─────────────────────────────────────╯")
        print()

        try:
            username = input("󰙯 请输入您的昵称: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not username:
            print("昵称不能为空")
            return
        config["user"]["name"] = username

        srv = config["server"]
        try:
            server_input = input(
                f"󰒋 服务器地址 [{srv['host']}:{srv['port']}]: "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            return
        if server_input:
            host, port = parse_server_addr(server_input)
            config["server"]["host"] = host
            config["server"]["port"] = port

        # 持久化
        save(config)
        print()
        print(f"✓ 配置已保存至 {config_path()}")
        print(f"  下次启动将直接连接 {server_url(config)}")
        print()

    url = server_url(config)
    client = ChatClient(config["user"]["name"], url)
    client.run()
    print("\n再见! 👋")


if __name__ == "__main__":
    main()
