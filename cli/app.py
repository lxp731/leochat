"""
ChatRoom CLI — 纯 Rich 版
═══════════════════════════════════════════════════════════
Rich 全渲染（Nerd Font 图标 + force_terminal）。
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

import socketio
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

console = Console(force_terminal=True, highlight=False)

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
CST = timezone(timedelta(hours=8))
SERVER_IP = os.environ.get("SERVER_IP", "127.0.0.1")
SERVER_PORT = os.environ.get("SERVER_PORT", "5000")
SERVER_URL = os.environ.get("CHAT_SERVER", f"http://{SERVER_IP}:{SERVER_PORT}")


class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._users: list[str] = []
        self._register_events()

    def _now(self) -> str:
        return datetime.now(CST).strftime("%H:%M")

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self.connected = True
            self.sio.emit("join", {"user": self.username})
            console.print(f"[bold magenta]󰄬 已连接至服务器: {SERVER_URL}[/bold magenta]")

        @self.sio.event
        def disconnect():
            self.connected = False
            console.print("[bold red]󰅚 与服务器断开连接[/bold red]")

        @self.sio.on("message")
        def on_message(data):
            user = data.get("user", "???")
            text = data.get("text", "")
            ts = data.get("time", self._now())
            msg = Text()
            msg.append(f"󱑎 {ts} ", style="cyan")
            if user == self.username:
                msg.append("󰙯 你 ", style="bold green")
            else:
                msg.append(f"󰙯 {user} ", style="bold yellow")
            msg.append(f"󰭹 {text}", style="white")
            console.print(msg)

        @self.sio.on("system")
        def on_system(data):
            content = data.get("text", "")
            icon = "󰋼"
            if "joined" in content:
                icon = "󰶼"
            elif "left" in content:
                icon = "󰶽"
            console.print(f"[bold magenta]{icon} {content}[/bold magenta]")

        @self.sio.on("error")
        def on_error(data):
            err = data.get("text", "错误")
            console.print(f"[bold red]󰅚 {err}[/bold red]")

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))

    def run(self) -> None:
        console.clear()
        console.print(Panel.fit(
            f"[bold cyan]󰭹 ChatRoom CLI (Pure Rich 版)[/bold cyan]\n"
            f"[cyan]󱑎 欢迎, {self.username}![/cyan]",
            border_style="blue", padding=(1, 2),
        ))

        try:
            self.sio.connect(SERVER_URL, wait_timeout=5)
        except Exception as exc:
            err = str(exc)
            if "refused" in err.lower():
                console.print("[bold red]无法连接服务器: 服务未启动或端口错误[/bold red]")
            else:
                console.print(f"[bold red]无法连接服务器: {err}[/bold red]")
            return

        def input_thread_func():
            while not self.exit_flag:
                try:
                    line = console.input(
                        f" [bold cyan]󰞷 {self.username} ❯ [/bold cyan]"
                    ).strip()
                    if not line:
                        continue
                    if line.startswith("/"):
                        cmd = line.lower()[1:]
                        if cmd in ("exit", "quit"):
                            self.exit_flag = True
                            self.sio.disconnect()
                            break
                        if cmd == "users":
                            ul = ", ".join(self._users) if self._users else "无"
                            console.print(f"[cyan]󰭿 在线: {ul}[/cyan]")
                            continue
                        if cmd == "help":
                            console.print("[yellow]命令: /users /exit /help[/yellow]")
                            continue
                        console.print(f"[red]未知命令: /{cmd}[/red]")
                        continue
                    if self.connected:
                        self.sio.emit("send_message", {
                            "user": self.username,
                            "text": line,
                            "time": self._now(),
                        })
                    else:
                        console.print("[bold red]󰅚 发送失败: 未连接[/bold red]")
                except (KeyboardInterrupt, EOFError):
                    self.exit_flag = True
                    self.sio.disconnect()
                    break

        threading.Thread(target=input_thread_func, daemon=True).start()

        # 主循环等待退出（非 sio.wait，避免死锁）
        while not self.exit_flag:
            time.sleep(0.1)

        console.print("\n[bold cyan]再见! 👋[/bold cyan]")


def main() -> None:
    console.clear()
    console.print(Panel.fit("💬 [bold cyan]极简聊天室[/bold cyan]", border_style="blue"))
    try:
        username = console.input("[bold yellow]󰙯 请输入您的昵称: [/bold yellow]").strip()
        if not username:
            console.print("[red]昵称不能为空[/red]")
            return
        client = ChatClient(username)
        client.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")


if __name__ == "__main__":
    main()
