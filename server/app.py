import os
import time
from collections import defaultdict

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

socketio = SocketIO(app, cors_allowed_origins="*")

# ── 简易速率限制 ──────────────────────────────────────────
MAX_MSG_LEN = 2000
RATE_LIMIT_WINDOW = 2          # 秒
RATE_LIMIT_MAX = 5             # 窗口内最大消息数
_client_timestamps: dict[str, list[float]] = defaultdict(list)

def _check_rate(sid: str) -> bool:
    now = time.time()
    ts = _client_timestamps[sid]
    # 清理过期时间戳
    ts[:] = [t for t in ts if now - t < RATE_LIMIT_WINDOW]
    ts.append(now)
    return len(ts) <= RATE_LIMIT_MAX


@app.route('/')
def index():
    return render_template('index.html')


# ── 连接 / 断线 ───────────────────────────────────────────
@socketio.on('connect')
def handle_connect(auth=None):
    print(f'[+] Client connected: {request.sid}')
    # 通知所有人（不含自己）
    emit('system', {'text': 'A new user has joined the chat.'}, broadcast=True, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    print(f'[-] Client disconnected: {request.sid}')
    emit('system', {'text': 'A user has left the chat.'}, broadcast=True)


# ── 消息转发 ──────────────────────────────────────────────
@socketio.on('send_message')
def handle_message(data):
    # 输入校验
    if not isinstance(data, dict):
        return
    user = str(data.get('user', 'Anonymous'))[:50]
    text = str(data.get('text', ''))[:MAX_MSG_LEN]
    if not text.strip():
        return

    # 速率限制
    if not _check_rate(request.sid):
        emit('error', {'text': 'Rate limit exceeded. Slow down.'})
        return

    print(f"[MSG] {user}: {text[:80]}{'...' if len(text)>80 else ''}")
    # broadcast=True + include_self=True → 发给所有人（包括发送者）
    emit('message', {'user': user, 'text': text}, broadcast=True, include_self=True)


if __name__ == '__main__':
    debug = os.environ.get('CHAT_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('CHAT_PORT', '5000'))
    socketio.run(app, host='0.0.0.0', port=port,
                 debug=debug, allow_unsafe_werkzeug=True)
