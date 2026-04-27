"""
ChatRoom CLI — 终端聊天客户端
═══════════════════════════════════════════════════════════
prompt_toolkit + 纯 ANSI 渲染，零额外依赖。
"""
import os
import sys
import threading
from datetime import datetime, timezone, timedelta

import socketio
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

# ── 配置 ──────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")
RECONNECT_BASE = 2
RECONNECT_MAX = 60

_STYLE = Style.from_dict({"prompt": "bold green"})

# ── ANSI 颜色 ─────────────────────────────────────────────
R = "\033[0m"       # reset
B = "\033[1m"       # bold
D = "\033[2m"       # dim
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BC = "\033[1;36m"   # bold cyan


class ChatClient:
    def __init__(self, username: str):
        self.username = username
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self.connected = False
        self._reconnect_attempt = 0
        self._users: list[str] = []
        self._register_events()

    def _now(self) -> str:
        return datetime.now(CST).strftime("%H:%M")

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self.connected = True
            self._reconnect_attempt = 0
            self.sio.emit("join", {"user": self.username})
            self._say("", f"{BC}ChatRoom / {R}{B}{self.username}{R}  "
                     f"{GREEN}●{R} {D}{SERVER_URL}{R}")
            self._say("green", "已连接到服务器")

        @self.sio.event
        def disconnect():
            self.connected = False
            self._say("red", "连接断开")
            if not self.exit_flag:
                self._try_reconnect()

        @self.sio.on("message")
        def on_message(data):
            self._print_msg(data)

        @self.sio.on("system")
        def on_system(data):
            self._say("yellow", data.get("text", ""))

        @self.sio.on("error")
        def on_error(data):
            self._say("red", data.get("text", "错误"))

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))
            if self._users:
                self._print_users()

    def _try_reconnect(self) -> None:
        def reconnect():
            delay = min(RECONNECT_BASE * (2 ** self._reconnect_attempt), RECONNECT_MAX)
            self._reconnect_attempt += 1
            self._say("yellow", f"将在 {delay}s 后重连 (第 {self._reconnect_attempt} 次)…")
            import time
            time.sleep(delay)
            if self.exit_flag:
                return
            try:
                self.sio.connect(SERVER_URL)
            except Exception as exc:
                self._say("red", f"重连失败: {exc}")
                if not self.exit_flag:
                    self._try_reconnect()
        threading.Thread(target=reconnect, daemon=True).start()

    # ── 输出 ──────────────────────────────────────────

    def _say(self, color: str, text: str) -> None:
        """打印一条带颜色的消息."""
        print_formatted_text(
            FormattedText([(f"bold ansi{color}" if color else "", f"  {text}")]),
            style=_STYLE,
        )

    def _print_msg(self, data: dict) -> None:
        user = data.get("user", "???")
        text = data.get("text", "")
        ts = data.get("time", "")
        parts = []
        if ts:
            parts.append(("", f" {D}{ts}{R} "))
        else:
            parts.append(("", " "))
        parts.append(("bold ansicyan", user))
        parts.append(("", f"  {text}"))
        print_formatted_text(FormattedText(parts), style=_STYLE)

    def _print_users(self) -> None:
        print_formatted_text(
            FormattedText([("bold ansicyan", "  ── 在线 ──")]),
            style=_STYLE,
        )
        for u in self._users:
            me = u == self.username
            dot = f"{GREEN}●{R}" if me else f"{D}○{R}"
            name = f"{B}{u}{R}" if me else u
            print_formatted_text(
                FormattedText([("", f"    {dot} {name}")]),
                style=_STYLE,
            )

    # ── 运行 ──────────────────────────────────────────

    def run(self) -> None:
        try:
            self.sio.connect(SERVER_URL)
        except Exception as exc:
            print_formatted_text(
                FormattedText([("bold ansired", f"无法连接服务器: {exc}")]),
                style=_STYLE,
            )
            sys.exit(1)

        session = PromptSession(history=InMemoryHistory())

        def input_loop():
            with patch_stdout():
                while not self.exit_flag:
                    try:
                        line = session.prompt(
                            [("class:prompt", f"You ({self.username}) > ")],
                            style=_STYLE,
                        ).strip()
                        if not line:
                            continue
                        if line.lower() in ("/exit", "/quit"):
                            self.exit_flag = True
                            break
                        if line.lower() == "/help":
                            self._say("yellow",
                                      "/exit 退出  /help 帮助  /users 列表  直接输入发送消息")
                            continue
                        if line.lower() == "/users":
                            if self._users:
                                self._print_users()
                            else:
                                self._say("yellow", "暂无在线用户")
                            continue
                        if self.connected:
                            self.sio.emit("send_message", {
                                "user": self.username,
                                "text": line,
                                "time": self._now(),
                            })
                        else:
                            self._say("red", "未连接，消息无法发送")
                    except (KeyboardInterrupt, EOFError):
                        self.exit_flag = True
                        break

        threading.Thread(target=input_loop, daemon=True).start()
        self.sio.wait()
        print_formatted_text(FormattedText([("bold ansicyan", "\n再见!")]), style=_STYLE)


def main() -> None:
    print(f"\n{BC}  ChatRoom CLI{R}\n")
    username = input(f"{B}用户名: {R}").strip()
    if not username:
        print(f"{RED}用户名不能为空{R}")
        sys.exit(1)
    if len(username) > 20:
        username = username[:20]
    ChatClient(username=username).run()


if __name__ == "__main__":
    main()
