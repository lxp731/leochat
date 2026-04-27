import socketio
import threading
import sys
import os
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.history import InMemoryHistory

SERVER_URL = "http://123.57.54.42:5000"
RECONNECT_DELAY = 5  # 秒

class ChatClient:
    def __init__(self, username: str, server_url: str):
        self.username = username
        self.server_url = server_url
        self.sio = socketio.Client(reconnection=False)  # 我们自己控制重连
        self.exit_flag = False
        self.session = PromptSession(history=InMemoryHistory())
        self.style = Style.from_dict({
            'username': 'ansiblue bold',
            'message': '',
            'system': 'ansiyellow italic',
            'prompt': 'ansigreen bold',
            'error': 'ansired bold',
        })
        self._register_events()

    def _register_events(self):
        @self.sio.event
        def connect():
            print_formatted_text(FormattedText([
                ('class:system', '[INFO] Connected to server.\n')
            ]), style=self.style)
            # 进入聊天室通知
            self.sio.emit('message', {'user': self.username, 'text': 'has joined the chat.'})

        @self.sio.event
        def disconnect():
            print_formatted_text(FormattedText([
                ('class:system', '\n[INFO] Disconnected from server.\n')
            ]), style=self.style)
            if not self.exit_flag:
                # 非主动退出，尝试重连
                print_formatted_text(FormattedText([
                    ('class:system', f'[INFO] Attempting to reconnect in {RECONNECT_DELAY} seconds...\n')
                ]), style=self.style)
                time.sleep(RECONNECT_DELAY)
                try:
                    self.sio.connect(self.server_url)
                except Exception as e:
                    print_formatted_text(FormattedText([
                        ('class:error', f'[ERROR] Reconnect failed: {e}\n')
                    ]), style=self.style)

        @self.sio.on('message')
        def on_message(data):
            # 避免消息格式异常导致崩溃
            user = data.get('user', 'Unknown')
            text = data.get('text', '')
            # 打印消息，自动换行且不打断输入
            formatted = FormattedText([
                ('class:username', f"[{user}] "),
                ('class:message', text)
            ])
            print_formatted_text(formatted, style=self.style)

    def run(self):
        try:
            self.sio.connect(self.server_url)
        except Exception as e:
            print_formatted_text(FormattedText([
                ('class:error', f'[ERROR] Could not connect to server: {e}\n')
            ]), style=self.style)
            sys.exit(1)

        # 启动输入线程
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()

        # 主线程等待 SocketIO 事件循环
        self.sio.wait()

    def _input_loop(self):
        with patch_stdout():
            while not self.exit_flag:
                try:
                    prompt_text = [('class:prompt', f'You ({self.username}): ')]
                    user_input = self.session.prompt(FormattedText(prompt_text)).strip()
                    if not user_input:
                        continue
                    if user_input.lower() in ['/exit', '/quit']:
                        print_formatted_text(FormattedText([
                            ('class:system', '[INFO] Exiting chat...\n')
                        ]), style=self.style)
                        self.exit_flag = True
                        self.sio.emit('message', {'user': self.username, 'text': 'has left the chat.'})
                        self.sio.disconnect()
                        break
                    elif user_input.lower() == '/help':
                        self._print_help()
                    else:
                        self.sio.emit('send_message', {'user': self.username, 'text': user_input})
                except (KeyboardInterrupt, EOFError):
                    print_formatted_text(FormattedText([
                        ('class:system', '\n[INFO] Keyboard interrupt received. Exiting chat...\n')
                    ]), style=self.style)
                    self.exit_flag = True
                    self.sio.emit('message', {'user': self.username, 'text': 'has left the chat.'})
                    self.sio.disconnect()
                    break

    def _print_help(self):
        help_text = """
        Available commands:
        /help       Show this help message
        /exit, /quit    Exit the chat
        """
        print_formatted_text(FormattedText([
            ('class:system', help_text)
        ]), style=self.style)

def main():
    username = input("Enter your username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    client = ChatClient(username=username, server_url=SERVER_URL)
    client.run()

if __name__ == "__main__":
    main()
