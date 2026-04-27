"""
ChatRoom CLI — 终端聊天客户端
═══════════════════════════════════════════════════════════
Rich 渲染消息 + prompt_toolkit 管理输入，互不干扰。
"""
import os
import sys
import threading
from datetime import datetime, timezone, timedelta

import socketio
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.box import ROUNDED, SIMPLE

CST = timezone(timedelta(hours=8))
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")
RECONNECT_BASE = 2
RECONNECT_MAX = 60

console = Console()
style = Style.from_dict({
    "prompt": "bold green",
})

# ── 消息 ──────────────────────────────────────────────────
class Msg:
    __slots__ = ("user", "text", "ts", "kind")
    def __init__(self, user="", text="", ts="", kind="msg"):
        self.user = user
        self.text = text
        self.ts = ts
        self.kind = kind


class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._reconnect_attempt = 0
        self._users: list[str] = []
        self._msg_history: list[Msg] = []   # 消息历史
        self._last_userlist: list[str] = []
        self._register_events()

    def _now(self) -> str:
        return datetime.now(CST).strftime("%H:%M")

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self.connected = True
            self._reconnect_attempt = 0
            self.sio.emit("join", {"user": self.username})
            self._print_header()
            self._print_status("已连接到服务器", "green")

        @self.sio.event
        def disconnect():
            self.connected = False
            self._print_status("连接断开", "red")
            if not self.exit_flag:
                self._try_reconnect()

        @self.sio.on("message")
        def on_message(data):
            msg = Msg(
                user=data.get("user", "???"),
                text=data.get("text", ""),
                ts=data.get("time", ""),
                kind="msg",
            )
            self._msg_history.append(msg)
            self._print_msg(msg)

        @self.sio.on("system")
        def on_system(data):
            text = data.get("text", "")
            msg = Msg(kind="system", text=text)
            self._msg_history.append(msg)
            self._print_system(text)

        @self.sio.on("error")
        def on_error(data):
            text = f"⚠ {data.get('text', 'Error')}"
            console.print(Text(text, style="bold red"), highlight=False)

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))
            self._last_userlist = list(self._users)
            if self._users:
                self._print_userlist()

    def _try_reconnect(self) -> None:
        def reconnect():
            delay = min(RECONNECT_BASE * (2 ** self._reconnect_attempt), RECONNECT_MAX)
            self._reconnect_attempt += 1
            self._print_status(f"将在 {delay}s 后重连 (第 {self._reconnect_attempt} 次)…", "yellow")
            import time
            time.sleep(delay)
            if self.exit_flag:
                return
            try:
                self.sio.connect(SERVER_URL)
            except Exception as exc:
                self._print_status(f"重连失败: {exc}", "red")
                if not self.exit_flag:
                    self._try_reconnect()

        t = threading.Thread(target=reconnect, daemon=True)
        t.start()

    # ── Rich 渲染 ──────────────────────────────────────

    def _print_header(self) -> None:
        """打印顶部标题栏."""
        status_dot = "[bold green]●[/]" if self.connected else "[bold red]●[/]"
        title = Text.assemble(
            ("💬 ChatRoom / ", "bold cyan"),
            (self.username, "bold white"),
            (f"    {status_dot} ", ""),
            (f"{SERVER_URL}", "dim"),
        )
        console.print(Panel(title, box=ROUNDED, border_style="cyan"), highlight=False)

    def _print_status(self, text: str, color: str) -> None:
        console.print(Text(f"  ─ {text}", style=f"dim italic {color}"), highlight=False)

    def _print_msg(self, msg: Msg) -> None:
        """打印一条聊天消息."""
        time_str = Text(f" {msg.ts} ", style="dim") if msg.ts else Text("")
        user_str = Text(f"{msg.user}", style="bold cyan")
        text_str = Text(f"  {msg.text}")
        line = Text.assemble(time_str, ("  ", ""), user_str, text_str)
        console.print(Align.left(line), highlight=False)

    def _print_system(self, text: str) -> None:
        console.print(Text(f"  ─ {text}", style="dim italic yellow"), highlight=False)

    def _print_userlist(self) -> None:
        """打印在线用户面板."""
        table = Table(box=SIMPLE, show_header=False, expand=False,
                      padding=(0, 2), collapse_padding=True)
        table.add_column(style="white")
        for u in self._users:
            icon = "[green]●[/]" if u == self.username else "[dim]●[/]"
            name = f"[bold]{u}[/]" if u == self.username else u
            table.add_row(f"{icon} {name}")
        panel = Panel(table, title="👥 在线",
                      border_style="cyan", box=ROUNDED, width=30)
        console.print(panel, highlight=False)

    # ── 运行 ──────────────────────────────────────────

    def run(self) -> None:
        try:
            self.sio.connect(SERVER_URL)
        except Exception as exc:
            console.print(Text(f"❌ 无法连接服务器: {exc}", style="bold red"), highlight=False)
            sys.exit(1)

        # 在 prompt_toolkit 的 patch_stdout 上下文中运行输入
        session = PromptSession(history=InMemoryHistory())

        def user_input_thread():
            with patch_stdout():
                while not self.exit_flag:
                    try:
                        line = session.prompt(
                            [("class:prompt", f"You ({self.username}) ➤ ")],
                            style=style,
                        ).strip()
                        if not line:
                            continue
                        if line.lower() in ("/exit", "/quit"):
                            self.exit_flag = True
                            break
                        if line.lower() == "/help":
                            self._print_system(
                                "命令: /exit 退出  /help 帮助  /users 列表\n"
                                "      直接输入文字即可发送消息"
                            )
                            continue
                        if line.lower() == "/users":
                            if self._users:
                                self._print_userlist()
                            else:
                                self._print_system("暂无在线用户")
                            continue
                        if self.connected:
                            self.sio.emit("send_message", {
                                "user": self.username,
                                "text": line,
                                "time": self._now(),
                            })
                        else:
                            self._print_status("未连接，消息无法发送", "red")
                    except (KeyboardInterrupt, EOFError):
                        self.exit_flag = True
                        break

        t = threading.Thread(target=user_input_thread, daemon=True)
        t.start()

        # 主线程跑 Socket.IO 事件循环
        self.sio.wait()
        console.print(Text("\n再见! 👋", style="bold cyan"), highlight=False)


def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]💬  ChatRoom CLI[/]\n\n"
        "[dim]Rich + prompt_toolkit + Socket.IO[/]",
        border_style="cyan", box=ROUNDED,
    ), highlight=False)

    username = console.input("[bold]请输入用户名: [/]").strip()
    if not username:
        console.print("[red]用户名不能为空[/]", highlight=False)
        sys.exit(1)
    if len(username) > 20:
        username = username[:20]

    client = ChatClient(username=username)
    client.run()


if __name__ == "__main__":
    main()
