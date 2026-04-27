"""
ChatRoom CLI — 终端聊天客户端
═══════════════════════════════════════════════════════════
自动检测终端 ANSI 支持，不支持时降级为纯文本。
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
from prompt_toolkit.shortcuts import print_formatted_text, clear
from prompt_toolkit.styles import Style

# ── 终端检测 ──────────────────────────────────────────────
_HAS_ANSI = (
    sys.stdout.isatty()
    and os.environ.get("TERM", "") not in ("", "dumb", "unknown")
    and os.environ.get("NO_COLOR", "") == ""
)
_STYLE = Style.from_dict({}) if _HAS_ANSI else Style.from_dict({"": ""})

# ── 颜色 ──────────────────────────────────────────────────
if _HAS_ANSI:
    R = "\033[0m"; B = "\033[1m"; D = "\033[2m"
    RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"; CYAN = "\033[36m"
    BC = "\033[1;36m"
else:
    R = B = D = RED = GREEN = YELLOW = CYAN = BC = ""


def _pt(cls: str, text: str) -> FormattedText:
    """构建 prompt_toolkit 格式化文本（ANSI 可用时带色，否则纯文本）."""
    if _HAS_ANSI:
        return FormattedText([(cls, text)])
    else:
        return FormattedText([("", text)])


# ── 配置 ──────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")
RECONNECT_BASE = 2
RECONNECT_MAX = 60


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
            clear()
            self._say("bold ansicyan",
                      f"ChatRoom / {B}{self.username}{R}  {GREEN}*{R}  {SERVER_URL}")
            self._say("", "已连接到服务器")

        @self.sio.event
        def disconnect():
            self.connected = False
            self._say("bold ansired", "连接断开")
            if not self.exit_flag:
                self._try_reconnect()

        @self.sio.on("message")
        def on_message(data):
            self._print_msg(data)

        @self.sio.on("system")
        def on_system(data):
            self._say("", data.get("text", ""))

        @self.sio.on("error")
        def on_error(data):
            self._say("bold ansired", data.get("text", "错误"))

        @self.sio.on("userlist")
        def on_userlist(data):
            self._users = list(data.get("users", []))
            if self._users:
                self._print_users()

    def _try_reconnect(self) -> None:
        def reconnect():
            delay = min(RECONNECT_BASE * (2 ** self._reconnect_attempt), RECONNECT_MAX)
            self._reconnect_attempt += 1
            self._say("", f"将在 {delay}s 后重连 (第 {self._reconnect_attempt} 次)…")
            import time
            time.sleep(delay)
            if self.exit_flag:
                return
            try:
                self.sio.connect(SERVER_URL)
            except Exception as exc:
                self._say("bold ansired", f"重连失败: {exc}")
                if not self.exit_flag:
                    self._try_reconnect()
        threading.Thread(target=reconnect, daemon=True).start()

    # ── 输出 ──────────────────────────────────────────

    def _say(self, cls: str, text: str) -> None:
        print_formatted_text(_pt(cls, f"  {text}"), style=_STYLE)

    def _print_msg(self, data: dict) -> None:
        user = data.get("user", "???")
        text = data.get("text", "")
        ts = data.get("time", "")
        line = f"  {D}{ts} {R}" if ts else "  "
        line += f"{CYAN}{user}{R}  {text}"
        print_formatted_text(_pt("", line), style=_STYLE)

    def _print_users(self) -> None:
        self._say("bold ansicyan", "--- 在线 ---")
        for u in self._users:
            if u == self.username:
                print_formatted_text(_pt("", f"    {GREEN}*{R} {B}{u}{R}"), style=_STYLE)
            else:
                print_formatted_text(_pt("", f"    - {u}"), style=_STYLE)

    # ── 运行 ──────────────────────────────────────────

    def run(self) -> None:
        try:
            self.sio.connect(SERVER_URL)
        except Exception as exc:
            print_formatted_text(
                _pt("bold ansired", f"无法连接服务器: {exc}"), style=_STYLE)
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
                            self.sio.disconnect()
                            break
                        if line.lower() == "/help":
                            self._say("", "命令: /exit 退出  /help 帮助  /users 列表")
                            continue
                        if line.lower() == "/users":
                            if self._users:
                                self._print_users()
                            else:
                                self._say("", "暂无在线用户")
                            continue
                        if self.connected:
                            self.sio.emit("send_message", {
                                "user": self.username,
                                "text": line,
                                "time": self._now(),
                            })
                        else:
                            self._say("bold ansired", "未连接，消息无法发送")
                    except (KeyboardInterrupt, EOFError):
                        self.exit_flag = True
                        self.sio.disconnect()
                        break

        threading.Thread(target=input_loop, daemon=True).start()
        self.sio.wait()
        print_formatted_text(_pt("", "\n再见!"), style=_STYLE)


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
