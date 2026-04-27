"""
ChatRoom CLI — 终端聊天客户端
═══════════════════════════════════════════════════════════
自动检测终端能力，Rich 渲染不可用时降级为纯文本。
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
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text

CST = timezone(timedelta(hours=8))
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")
RECONNECT_BASE = 2
RECONNECT_MAX = 60

# ── Rich: 默认关闭，CHAT_RICH=1 开启（需终端完整支持 ANSI） ─
_rich_ok = os.environ.get("CHAT_RICH", "").lower() in ("1", "true", "yes")
if _rich_ok:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.box import ROUNDED, SIMPLE
    _rich_console = Console(highlight=False)

# prompt_toolkit 样式（轻量，始终可用）
_PROMPT_STYLE = Style.from_dict({"prompt": "bold green"})

# ── 颜色常量（纯 ANSI，Rich 不可用时的降级） ────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_BOLD_CYAN = "\033[1;36m"
C_BOLD_GREEN = "\033[1;32m"
C_DIM_YELLOW = "\033[2;33m"
C_DIM_RED = "\033[2;31m"


def _colorize(text: str, color: str) -> str:
    """用纯 ANSI 包裹文字，在 Rich 不可用时使用."""
    return f"{color}{text}{C_RESET}"


class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._reconnect_attempt = 0
        self._users: list[str] = []
        self._header_printed = False
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
            self._print_msg(data)

        @self.sio.on("system")
        def on_system(data):
            self._print_status(data.get("text", ""), "yellow")

        @self.sio.on("error")
        def on_error(data):
            self._print_status(data.get("text", "错误"), "red")

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))
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

    # ── 输出（自动选择 Rich 或纯 ANSI） ────────────────

    def _print_header(self) -> None:
        if self._header_printed:
            return
        self._header_printed = True
        status = "●" if self.connected else "○"
        if _rich_ok:
            dot = Text("● " if self.connected else "○ ", style="bold green" if self.connected else "bold red")
            title = Text.assemble(
                ("ChatRoom / ", "bold cyan"),
                (self.username, "bold white"),
                ("    ", ""),
                dot,
                (SERVER_URL, "dim"),
            )
            _rich_console.print(Panel(title, box=ROUNDED, border_style="cyan"))
        else:
            header = (
                f"{C_BOLD_CYAN}ChatRoom / {C_RESET}"
                f"{C_BOLD}{self.username}{C_RESET}    "
                f"{C_BOLD_GREEN}{status}{C_RESET} "
                f"{C_DIM}{SERVER_URL}{C_RESET}"
            )
            print_formatted_text(FormattedText([("", header)]))

    def _print_status(self, text: str, color: str) -> None:
        colors = {"green": C_GREEN, "red": C_RED, "yellow": C_YELLOW}
        c = colors.get(color, C_RESET)
        print_formatted_text(
            FormattedText([(f"fg:{color}", f"  ─ {text}")]),
            style=_PROMPT_STYLE,
        )

    def _print_msg(self, data: dict) -> None:
        user = data.get("user", "???")
        text = data.get("text", "")
        ts = data.get("time", "")
        if _rich_ok:
            time_part = Text(f" {ts} ", style="dim") if ts else Text("")
            line = Text.assemble(
                time_part,
                ("  ", ""),
                (f"{user}", "bold cyan"),
                (f"  {text}", ""),
            )
            _rich_console.print(Align.left(line))
        else:
            ts_str = f"{C_DIM}{ts}{C_RESET} " if ts else ""
            print_formatted_text(
                FormattedText([
                    ("", f"  {ts_str}"),
                    ("bold ansicyan", f"{user}"),
                    ("", f"  {text}"),
                ]),
                style=_PROMPT_STYLE,
            )

    def _print_userlist(self) -> None:
        lines = []
        for u in self._users:
            marker = "[*]" if u == self.username else "[ ]"
            lines.append(f"    {marker} {u}")
        if _rich_ok:
            table = Table(box=SIMPLE, show_header=False, padding=(0, 2))
            table.add_column(style="white")
            for u in self._users:
                icon = "●" if u == self.username else "○"
                name = u
                table.add_row(f"{icon} {name}")
            _rich_console.print(
                Panel(table, title="在线", border_style="cyan", box=ROUNDED)
            )
        else:
            print_formatted_text(
                FormattedText([("bold ansicyan", "  👥 在线用户:")]),
                style=_PROMPT_STYLE,
            )
            for u in self._users:
                marker = f"{C_BOLD_GREEN}●{C_RESET}" if u == self.username else f"{C_DIM}○{C_RESET}"
                name = f"{C_BOLD if u == self.username else ''}{u}{C_RESET if u == self.username else ''}"
                print_formatted_text(
                    FormattedText([("", f"    {marker} {name}")]),
                    style=_PROMPT_STYLE,
                )

    # ── 运行 ──────────────────────────────────────────

    def run(self) -> None:
        try:
            self.sio.connect(SERVER_URL)
        except Exception as exc:
            print_formatted_text(
                FormattedText([("bold ansired", f"无法连接服务器: {exc}")]),
                style=_PROMPT_STYLE,
            )
            sys.exit(1)

        session = PromptSession(history=InMemoryHistory())

        def input_loop():
            with patch_stdout():
                while not self.exit_flag:
                    try:
                        line = session.prompt(
                            [("class:prompt", f"You ({self.username}) > ")],
                            style=_PROMPT_STYLE,
                        ).strip()
                        if not line:
                            continue
                        if line.lower() in ("/exit", "/quit"):
                            self.exit_flag = True
                            break
                        if line.lower() == "/help":
                            self._print_status(
                                "/exit 退出  /help 帮助  /users 列表  直接输入发送消息",
                                "yellow",
                            )
                            continue
                        if line.lower() == "/users":
                            if self._users:
                                self._print_userlist()
                            else:
                                self._print_status("暂无在线用户", "yellow")
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

        t = threading.Thread(target=input_loop, daemon=True)
        t.start()
        self.sio.wait()

        print_formatted_text(
            FormattedText([("bold ansicyan", "\n再见!")]),
            style=_PROMPT_STYLE,
        )


def main() -> None:
    banner = (
        f"{C_BOLD_CYAN}╔════════════════════════╗{C_RESET}\n"
        f"{C_BOLD_CYAN}║  ChatRoom CLI          ║{C_RESET}\n"
        f"{C_BOLD_CYAN}╚════════════════════════╝{C_RESET}\n"
    )
    print(banner)

    username = input(f"{C_BOLD}用户名: {C_RESET}").strip()
    if not username:
        print(f"{C_RED}用户名不能为空{C_RESET}")
        sys.exit(1)
    if len(username) > 20:
        username = username[:20]

    client = ChatClient(username=username)
    client.run()


if __name__ == "__main__":
    main()
