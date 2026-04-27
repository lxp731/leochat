"""ChatRoom CLI Client — 终端聊天客户端."""
import os
import sys
import threading

import socketio
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

# ── 配置（通过环境变量覆盖） ──────────────────────────────
SERVER_URL = os.environ.get("CHAT_SERVER", "http://127.0.0.1:5000")
RECONNECT_BASE = 2    # 初始重连间隔（秒）
RECONNECT_MAX = 60    # 最大重连间隔

style = Style.from_dict({
    "username": "ansiblue bold",
    "message": "",
    "system": "ansiyellow italic",
    "prompt": "ansigreen bold",
    "error": "ansired bold",
})


class ChatClient:
    def __init__(self, username: str, server_url: str):
        self.username = username
        self.server_url = server_url
        self.sio = socketio.Client(reconnection=False)
        self.exit_flag = False
        self._reconnect_attempt = 0
        self.session = PromptSession(history=InMemoryHistory())
        self._register_events()

    def _log(self, cls: str, msg: str) -> None:
        print_formatted_text([(f"class:{cls}", msg)], style=style)

    def _register_events(self) -> None:
        @self.sio.event
        def connect():
            self._reconnect_attempt = 0
            self._log("system", "[CONNECTED] 已连接到服务器\n")

        @self.sio.event
        def disconnect():
            self._log("system", "[DISCONNECTED] 连接断开\n")
            if self.exit_flag:
                return
            self._try_reconnect()

        @self.sio.on("message")
        def on_message(data):
            user = data.get("user", "???")
            text = data.get("text", "")
            print_formatted_text(
                [("class:username", f"[{user}] "), ("class:message", text)],
                style=style,
            )

        @self.sio.on("system")
        def on_system(data):
            text = data.get("text", "")
            print_formatted_text([("class:system", f"[INFO] {text}\n")], style=style)

        @self.sio.on("error")
        def on_error(data):
            text = data.get("text", "")
            print_formatted_text([("class:error", f"[ERROR] {text}\n")], style=style)

    def _try_reconnect(self) -> None:
        """在独立线程中重连，避免阻塞事件循环."""
        def reconnect():
            # 指数退避
            delay = min(RECONNECT_BASE * (2 ** self._reconnect_attempt), RECONNECT_MAX)
            self._reconnect_attempt += 1
            self._log("system", f"[RECONNECT] {delay}s 后尝试重连 (第 {self._reconnect_attempt} 次)...\n")
            import time
            time.sleep(delay)
            if self.exit_flag:
                return
            try:
                self.sio.connect(self.server_url)
            except Exception as exc:
                self._log("error", f"[RECONNECT] 重连失败: {exc}\n")
                if not self.exit_flag:
                    self._try_reconnect()

        t = threading.Thread(target=reconnect, daemon=True)
        t.start()

    def run(self) -> None:
        try:
            self.sio.connect(self.server_url)
        except Exception as exc:
            self._log("error", f"[FATAL] 无法连接服务器: {exc}\n")
            sys.exit(1)

        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()
        self.sio.wait()

    def _input_loop(self) -> None:
        with patch_stdout():
            while not self.exit_flag:
                try:
                    prompt = [("class:prompt", f"You ({self.username}): ")]
                    user_input = self.session.prompt(prompt).strip()
                    if not user_input:
                        continue

                    if user_input.lower() in ("/exit", "/quit"):
                        self._log("system", "[INFO] 正在退出...\n")
                        self.exit_flag = True
                        self.sio.disconnect()
                        break

                    if user_input.lower() == "/help":
                        self._log("system", self._help_text())
                    else:
                        self.sio.emit("send_message",
                                      {"user": self.username, "text": user_input})
                except (KeyboardInterrupt, EOFError):
                    self._log("system", "\n[INFO] 收到中断信号，正在退出...\n")
                    self.exit_flag = True
                    self.sio.disconnect()
                    break

    @staticmethod
    def _help_text() -> str:
        return """
可用命令:
  /exit, /quit    退出聊天
  /help           显示此帮助
按下 Ctrl+C 也可退出
"""


def main() -> None:
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)
    client = ChatClient(username=username, server_url=SERVER_URL)
    client.run()


if __name__ == "__main__":
    main()
