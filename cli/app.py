"""
ChatRoom CLI — 终端聊天客户端
═══════════════════════════════════════════════════════════
基于 Rich + Socket.IO 的专业终端 UI。
"""
import os
import sys
import threading
from queue import Queue
from datetime import datetime, timezone, timedelta

import socketio
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
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


# ── 消息类型 ──────────────────────────────────────────────
class Msg:
    __slots__ = ("user", "text", "ts", "kind")
    def __init__(self, user="", text="", ts="", kind="msg"):
        self.user = user
        self.text = text
        self.ts = ts
        self.kind = kind  # msg / system / error


# ── 客户端 ────────────────────────────────────────────────
class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._reconnect_attempt = 0
        self._msg_queue: Queue = Queue()
        self._input_queue: Queue = Queue()
        self._users: list[str] = []
        self._register_events()

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self.connected = True
            self._reconnect_attempt = 0
            self._msg_queue.put(Msg(kind="system", text="已连接到服务器"))
            # 注册用户名
            self.sio.emit("join", {"user": self.username})

        @self.sio.event
        def disconnect():
            self.connected = False
            self._msg_queue.put(Msg(kind="system", text="连接断开"))
            if not self.exit_flag:
                self._try_reconnect()

        @self.sio.on("message")
        def on_message(data):
            self._msg_queue.put(Msg(
                user=data.get("user", "???"),
                text=data.get("text", ""),
                ts=data.get("time", ""),
                kind="msg",
            ))

        @self.sio.on("system")
        def on_system(data):
            self._msg_queue.put(Msg(kind="system", text=data.get("text", "")))

        @self.sio.on("error")
        def on_error(data):
            self._msg_queue.put(Msg(
                kind="error",
                text=f"⚠ {data.get('text', 'Unknown error')}",
            ))

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))

    def _try_reconnect(self) -> None:
        def reconnect():
            delay = min(RECONNECT_BASE * (2 ** self._reconnect_attempt), RECONNECT_MAX)
            self._reconnect_attempt += 1
            self._msg_queue.put(Msg(
                kind="system",
                text=f"将在 {delay}s 后重连 (第 {self._reconnect_attempt} 次)…",
            ))
            import time
            time.sleep(delay)
            if self.exit_flag:
                return
            try:
                self.sio.connect(SERVER_URL)
            except Exception as exc:
                self._msg_queue.put(Msg(kind="error", text=f"重连失败: {exc}"))
                if not self.exit_flag:
                    self._try_reconnect()

        t = threading.Thread(target=reconnect, daemon=True)
        t.start()

    def _now(self) -> str:
        return datetime.now(CST).strftime("%H:%M")

    # ── Rich UI 渲染 ───────────────────────────────────
    def _render(self) -> Layout:
        root = Layout()
        root.split_column(
            Layout(self._header(), size=3, name="header"),
            Layout(name="body"),
            Layout(self._footer(), size=3, name="footer"),
        )
        root["body"].split_row(
            Layout(self._messages(), name="messages", ratio=3),
            Layout(self._sidebar(), name="sidebar", ratio=1),
        )
        return root

    def _header(self) -> Panel:
        status = "[bold green]● 在线[/]" if self.connected else "[bold red]● 离线[/]"
        text = Text.assemble(
            ("💬 ChatRoom / ", "bold cyan"),
            (f"{self.username}", "bold white"),
            ("    ", ""),
            (status, ""),
            ("    ", ""),
            (f"⌂ {SERVER_URL}", "dim"),
        )
        return Panel(text, box=ROUNDED, border_style="cyan")

    def _sidebar(self) -> Panel:
        table = Table(box=SIMPLE, show_header=True, header_style="bold cyan", expand=True)
        table.add_column("在线用户", style="white")
        if self._users:
            for u in self._users:
                icon = "[green]●[/]" if u == self.username else "[dim]●[/]"
                name = f"[bold]{u}[/]" if u == self.username else u
                table.add_row(f"{icon} {name}")
        else:
            table.add_row("[dim]— 暂无 —[/]")
        return Panel(table, title="👥 在线", border_style="cyan", box=ROUNDED)

    def _messages(self) -> Panel:
        """组装最近的消息显示."""
        items = []
        while not self._msg_queue.empty():
            items.append(self._msg_queue.get_nowait())

        if not items:
            content = Align.center(
                "[dim italic]欢迎来到 ChatRoom! 输入消息开始聊天。[/]",
                vertical="middle",
            )
        else:
            lines: list[Text] = []
            for m in items[-200:]:  # 最多显示 200 条
                if m.kind == "system":
                    lines.append(Text(f"  ─ {m.text}", style="dim italic yellow"))
                elif m.kind == "error":
                    lines.append(Text(f"  ⚠ {m.text}", style="bold red"))
                else:
                    ts = f"[dim]{m.ts}[/dim]" if m.ts else ""
                    time_part = Text.from_markup(f" {ts} ") if ts else Text("")
                    user_part = Text(f"{m.user}", style="bold cyan")
                    text_part = Text(f"  {m.text}")
                    line = Text.assemble(
                        (f"{'  ' if not ts else ''}", ""),
                        time_part, ("  ", ""), user_part, text_part,
                    )
                    lines.append(line)
            content = Text("\n").join(lines) if lines else Text("")

        return Panel(content, title="📋 消息", border_style="cyan", box=ROUNDED)

    def _footer(self) -> Panel:
        hint = Text("输入消息后回车发送  |  /exit 退出  |  /help 帮助", style="dim")
        return Panel(hint, box=ROUNDED, border_style="cyan")

    # ── 输入循环 ──────────────────────────────────────
    def _input_loop(self) -> None:
        """在独立线程中读取用户输入."""
        while not self.exit_flag:
            try:
                raw = console.input(f"[bold green]You ({self.username}) ➤[/] ")
                self._input_queue.put(raw.strip())
            except (KeyboardInterrupt, EOFError):
                self.exit_flag = True
                break

    # ── 运行 ──────────────────────────────────────────
    def run(self) -> None:
        try:
            self.sio.connect(SERVER_URL)
        except Exception as exc:
            console.print(f"[bold red]无法连接服务器: {exc}[/]")
            sys.exit(1)

        # 启动输入线程
        input_t = threading.Thread(target=self._input_loop, daemon=True)
        input_t.start()

        # Rich Live 渲染循环
        with Live(self._render(), console=console, refresh_per_second=8,
                  screen=True, transient=False) as live:
            while not self.exit_flag:
                # 处理输入
                if not self._input_queue.empty():
                    cmd = self._input_queue.get_nowait()
                    if not cmd:
                        continue
                    if cmd.lower() in ("/exit", "/quit"):
                        self.exit_flag = True
                        break
                    if cmd.lower() == "/help":
                        self._msg_queue.put(Msg(kind="system", text="""
命令:  /exit 退出  /help 帮助  /users 用户列表
直接输入文字即可发送消息""".strip()))
                        continue
                    if cmd.lower() == "/users":
                        ulist = ", ".join(self._users) if self._users else "无"
                        self._msg_queue.put(Msg(kind="system", text=f"在线: {ulist}"))
                        continue
                    # 发送消息
                    if self.connected:
                        self.sio.emit("send_message", {
                            "user": self.username,
                            "text": cmd,
                            "time": self._now(),
                        })
                    else:
                        self._msg_queue.put(Msg(kind="error", text="未连接，消息无法发送"))

                # 更新 UI
                live.update(self._render())

        self.sio.disconnect()


def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]💬  ChatRoom CLI[/]\n\n"
        "[dim]专业终端聊天客户端 | Rich + Socket.IO[/]",
        border_style="cyan", box=ROUNDED,
    ))

    username = console.input("[bold]请输入用户名: [/]").strip()
    if not username:
        console.print("[red]用户名不能为空[/]")
        sys.exit(1)
    if len(username) > 20:
        username = username[:20]

    client = ChatClient(username=username)
    client.run()


if __name__ == "__main__":
    main()
