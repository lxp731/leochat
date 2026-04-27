"""
ChatRoom CLI — Rich + prompt_toolkit 混合版
═══════════════════════════════════════════════════════════
Rich 渲染消息 + prompt_toolkit 管理输入（线程安全）。
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from queue import Queue

import socketio
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

console = Console(force_terminal=True, highlight=False)
CST = timezone(timedelta(hours=8))
STYLE = Style.from_dict({"prompt": "bold cyan"})


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
SERVER_URL = os.environ.get(
    "CHAT_SERVER",
    f"http://{os.environ.get('SERVER_IP','127.0.0.1')}:{os.environ.get('SERVER_PORT','5000')}",
)


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
        self._users: list[str] = []
        self._inbox: Queue = Queue()
        self._register_events()

    def _now(self) -> str:
        return datetime.now(CST).strftime("%H:%M")

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self.connected = True
            self.sio.emit("join", {"user": self.username})
            self._inbox.put(Msg(kind="system", text="已连接至服务器"))

        @self.sio.event
        def disconnect():
            self.connected = False
            self._inbox.put(Msg(kind="system", text="与服务器断开连接"))

        @self.sio.on("message")
        def on_message(data):
            self._inbox.put(Msg(
                user=data.get("user", "???"),
                text=data.get("text", ""),
                ts=data.get("time", self._now()),
                kind="msg",
            ))

        @self.sio.on("system")
        def on_system(data):
            text = data.get("text", "")
            self._inbox.put(Msg(kind="system", text=text))

        @self.sio.on("error")
        def on_error(data):
            self._inbox.put(Msg(kind="error", text=data.get("text", "错误")))

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))

    def _render_msg(self, msg: Msg) -> None:
        if msg.kind == "system":
            icon = "● "
            if "joined" in msg.text:
                icon = "+ "
            elif "left" in msg.text:
                icon = "- "
            console.print(f"[dim magenta]{icon}{msg.text}[/dim magenta]")
        elif msg.kind == "error":
            console.print(f"[bold red]✗ {msg.text}[/bold red]")
        else:
            t = Text()
            t.append(f" {msg.ts} ", style="dim cyan")
            is_me = msg.user == self.username
            if is_me:
                t.append(f"{msg.user} ", style="bold green")
            else:
                t.append(f"{msg.user} ", style="bold yellow")
            t.append(msg.text, style="white")
            console.print(t)

    def _drain_inbox(self) -> None:
        while not self._inbox.empty():
            self._render_msg(self._inbox.get_nowait())

    def run(self) -> None:
        console.clear()
        console.print(Panel.fit(
            f"[bold cyan]ChatRoom CLI[/bold cyan]\n[dim]欢迎, {self.username}![/dim]",
            border_style="blue", padding=(1, 2),
        ))

        try:
            self.sio.connect(SERVER_URL, transports=["websocket", "polling"], wait_timeout=5)
        except Exception as exc:
            err = str(exc)
            if "refused" in err.lower():
                console.print("[bold red]无法连接服务器: 服务未启动或端口错误[/bold red]")
            else:
                console.print(f"[bold red]无法连接服务器: {err}[/bold red]")
            return

        session = PromptSession(history=InMemoryHistory())

        def input_loop():
            with patch_stdout():
                while not self.exit_flag:
                    try:
                        line = session.prompt(
                            [("class:prompt", f"{self.username} ❯ ")],
                            style=STYLE,
                        ).strip()
                        if not line:
                            continue
                        if line.startswith("/"):
                            cmd = line[1:].lower()
                            if cmd in ("exit", "quit"):
                                self.exit_flag = True
                                self.sio.disconnect()
                                break
                            if cmd == "users":
                                ul = ", ".join(self._users) if self._users else "无"
                                self._inbox.put(Msg(kind="system", text=f"在线: {ul}"))
                                continue
                            if cmd == "help":
                                self._inbox.put(Msg(kind="system", text="命令: /users /exit /help"))
                                continue
                            self._inbox.put(Msg(kind="error", text=f"未知命令: /{cmd}"))
                            continue
                        if self.connected:
                            self.sio.emit("send_message", {
                                "user": self.username,
                                "text": line,
                                "time": self._now(),
                            })
                        else:
                            self._inbox.put(Msg(kind="error", text="未连接，发送失败"))
                    except (KeyboardInterrupt, EOFError):
                        self.exit_flag = True
                        self.sio.disconnect()
                        break

        threading.Thread(target=input_loop, daemon=True).start()

        while not self.exit_flag:
            self._drain_inbox()
            time.sleep(0.05)
        self.sio.disconnect()

        console.print("\n[bold cyan]再见![/bold cyan]")


def main() -> None:
    console.clear()
    console.print(Panel.fit("💬 [bold cyan]ChatRoom[/bold cyan]", border_style="blue"))
    try:
        username = console.input("[bold yellow]请输入昵称: [/bold yellow]").strip()
        if not username:
            console.print("[red]昵称不能为空[/red]")
            return
        ChatClient(username).run()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")


if __name__ == "__main__":
    main()
