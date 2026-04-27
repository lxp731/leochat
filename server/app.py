"""
ChatRoom — 轻量实时聊天服务器
─────────────────────────────────
Flask + Socket.IO, 支持速率限制、在线用户列表、环境变量配置。
"""
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request # type: ignore
from flask_socketio import SocketIO, emit # type: ignore

# ── 配置 ──────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
CHAT_DEBUG = os.environ.get("CHAT_DEBUG", "false").lower() in ("1", "true", "yes")
CHAT_PORT = int(os.environ.get("CHAT_PORT", "5000"))
MAX_MSG_LEN = 2000
MAX_NAME_LEN = 20
RATE_WINDOW = 2          # 速率限制窗口 (秒)
RATE_MAX = 5             # 窗口内最大消息数

CST = timezone(timedelta(hours=8))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")

# ── 状态 ──────────────────────────────────────────────────
_client_timestamps: dict[str, list[float]] = defaultdict(list)
_sid_to_user: dict[str, str] = {}          # sid → username
_user_to_sids: dict[str, set[str]] = defaultdict(set)


def _now_str() -> str:
    return datetime.now(CST).strftime("%H:%M")


def _broadcast_userlist() -> None:
    users = list(dict.fromkeys(_sid_to_user.values()))
    emit("userlist", {"users": users}, broadcast=True)


def _check_rate(sid: str) -> bool:
    now = time.time()
    ts = _client_timestamps[sid]
    ts[:] = [t for t in ts if now - t < RATE_WINDOW]
    ts.append(now)
    return len(ts) <= RATE_MAX


# ── HTTP ──────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── 连接 / 断线 ───────────────────────────────────────────
@socketio.on("connect")
def handle_connect(auth=None):
    print(f"[+] {request.sid} connected")


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    username = _sid_to_user.pop(sid, None)
    if username:
        _user_to_sids[username].discard(sid)
        if not _user_to_sids[username]:
            del _user_to_sids[username]
            emit("system", {"text": f"{username} has left the chat."}, broadcast=True)
        _broadcast_userlist()
    print(f"[-] {sid} disconnected ({username or 'unknown'})")


# ── 用户注册 ──────────────────────────────────────────────
@socketio.on("join")
def handle_join(data):
    if not isinstance(data, dict):
        return
    username = str(data.get("user", ""))[:MAX_NAME_LEN].strip()
    if not username:
        return

    sid = request.sid
    old_name = _sid_to_user.get(sid)

    if old_name and old_name != username:
        _user_to_sids[old_name].discard(sid)
        if not _user_to_sids[old_name]:
            del _user_to_sids[old_name]

    _sid_to_user[sid] = username
    _user_to_sids[username].add(sid)

    if username != old_name:
        emit("system", {"text": f"{username} has joined the chat."}, broadcast=True)
    _broadcast_userlist()


# ── 消息 ──────────────────────────────────────────────────
@socketio.on("send_message")
def handle_message(data):
    if not isinstance(data, dict):
        return

    user = str(data.get("user", "Anonymous"))[:MAX_NAME_LEN].strip()
    text = str(data.get("text", ""))[:MAX_MSG_LEN]
    ts = data.get("time") or _now_str()

    if not user or not text.strip():
        return

    if not _check_rate(request.sid):
        emit("error", {"text": "发送太快，请稍候。"})
        return

    # 自动注册用户名
    sid = request.sid
    if sid not in _sid_to_user or _sid_to_user[sid] != user:
        old = _sid_to_user.get(sid)
        if old:
            _user_to_sids[old].discard(sid)
        _sid_to_user[sid] = user
        _user_to_sids[user].add(sid)
        _broadcast_userlist()

    print(f"[MSG] {user}: {text[:80]}{'…' if len(text) > 80 else ''}")
    emit("message", {"user": user, "text": text, "time": ts},
         broadcast=True, include_self=True)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=CHAT_PORT,
                 debug=CHAT_DEBUG, allow_unsafe_werkzeug=True)
